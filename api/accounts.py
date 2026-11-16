"""Cookie sessions and first-run account setup; printer tokens remain independent."""
import hashlib, hmac, secrets, time, uuid, re, os, ipaddress
from urllib.parse import urlsplit
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

COOKIE='fajny_session'
TTL=12*60*60
hasher=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1)
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
class Login(BaseModel):
    login:str=Field(min_length=1,max_length=254)
    password:str=Field(min_length=1,max_length=128)
class Profile(BaseModel):
    email:str=Field(max_length=254)
    nickname:str=Field(min_length=1,max_length=60)
    password:str=Field(min_length=10,max_length=128)
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):
        v=v.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('Zadaj platnú e-mailovú adresu.')
        return v
    @field_validator('nickname')
    @classmethod
    def nickname_valid(cls,v):
        v=v.strip()
        if not v or any(ord(c)<32 for c in v):raise ValueError('Zadaj platnú prezývku.')
        return v
class Settings(BaseModel):
    registration_enabled:bool=Field(strict=True)

def install(app,transaction,admin_token,config=None):
    config = config or {}
    maintenance_cidrs = [ipaddress.ip_network(value.strip()) for value in str(config.get("MAINTENANCE_CIDRS", os.environ.get("MAINTENANCE_CIDRS", ""))).split(",") if value.strip()]
    public_origin = str(config.get("PUBLIC_ORIGIN", os.environ.get("PUBLIC_ORIGIN", ""))).rstrip("/")
    def initialize():
        with transaction() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,nickname TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,must_setup INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS account_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS login_failures(key TEXT NOT NULL,at REAL NOT NULL);''')
            c.execute("INSERT OR IGNORE INTO auth_settings VALUES('registration_enabled','false')")
            if c.execute('SELECT count(*) FROM users').fetchone()[0]==0:
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',(str(uuid.uuid4()),None,'admin',hasher.hash('admin'),'admin'))
    def origin(request):
        value=request.headers.get('origin')
        if value:
            parsed=urlsplit(value)
            expected = public_origin or str(request.base_url).rstrip('/')
            if value.rstrip('/').lower() != expected.lower() or parsed.scheme not in ('http','https'):
                raise HTTPException(403,'Cross-origin request rejected')
    def public(row):return {k:(bool(row[k]) if k=='must_setup' else row[k]) for k in ('id','email','nickname','role','must_setup')}
    def get_session(request):
        token=request.cookies.get(COOKIE,'')
        if not token or len(token)>200:raise HTTPException(401,'Prihlás sa do štúdia.')
        with transaction() as c:
            r=c.execute('SELECT u.*,s.csrf,s.expires FROM account_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?',(sha(token),)).fetchone()
            if not r or r['expires']<time.time():raise HTTPException(401,'Prihlásenie vypršalo.')
            return dict(r)
    def csrf(request,row):
        origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']):raise HTTPException(403,'Neplatná ochrana požiadavky. Obnov stránku.')
    def access(request,admin_only=False):
        header=request.headers.get('authorization','')
        if header.startswith('Bearer ') and hmac.compare_digest(sha(header[7:]),sha(admin_token)):
            if maintenance_cidrs:
                try: permitted = any(ipaddress.ip_address(request.client.host) in network for network in maintenance_cidrs)
                except (ValueError, AttributeError): permitted = False
                if not permitted: raise HTTPException(403, 'Maintenance access is restricted to the management network')
            return None
        row=get_session(request)
        if row['must_setup']:raise HTTPException(403,'Najprv dokonči nastavenie účtu.')
        if request.method not in ('GET','HEAD','OPTIONS'):csrf(request,row)
        if admin_only and row['role']!='admin':raise HTTPException(403,'Vyžaduje sa správca.')
        return row
    def workspace(request:Request):return access(request)
    def administrator(request:Request):return access(request,True)
    def issue(c,user_id,response):
        token=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32)
        c.execute('DELETE FROM account_sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO account_sessions VALUES(?,?,?,?)',(sha(token),user_id,nonce,time.time()+TTL))
        response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,secure=True,samesite='lax',path='/')
        return nonce
    @app.get('/api/auth/config')
    def config():
        with transaction() as c:return {'registration_enabled':c.execute("SELECT value FROM auth_settings WHERE key='registration_enabled'").fetchone()[0]=='true'}
    @app.post('/api/auth/login')
    def login(body:Login,request:Request,response:Response):
        origin(request);name=body.login.strip().lower();ip=request.client.host if request.client else 'unknown';key=sha(ip+'|'+name)
        with transaction() as c:
            c.execute('DELETE FROM login_failures WHERE at<?',(time.time()-900,))
            if c.execute('SELECT count(*) FROM login_failures WHERE key=?',(key,)).fetchone()[0]>=5:raise HTTPException(429,'Priveľa pokusov. Skús to o 15 minút.')
            row=c.execute("SELECT * FROM users WHERE email=? OR (email IS NULL AND must_setup=1 AND ?='admin')",(name,name)).fetchone()
            valid=False
            if row:
                try:valid=hasher.verify(row['password_hash'],body.password)
                except (VerificationError,InvalidHashError):pass
            if not valid:c.execute('INSERT INTO login_failures VALUES(?,?)',(key,time.time()))
            else:
                c.execute('DELETE FROM login_failures WHERE key=?',(key,));nonce=issue(c,row['id'],response)
        if not valid:raise HTTPException(401,'Nesprávne prihlasovacie údaje.')
        return {'user':public(row),'csrf_token':nonce}
    @app.get('/api/auth/me')
    def me(request:Request):
        row=get_session(request);return {'user':public(row),'csrf_token':row['csrf']}
    @app.post('/api/auth/setup')
    def setup(body:Profile,request:Request,response:Response):
        row=get_session(request);csrf(request,row)
        if not row['must_setup']:raise HTTPException(409,'Účet je už nastavený.')
        if body.password=='admin':raise HTTPException(422,'Zvoľ nové heslo.')
        encoded=hasher.hash(body.password)
        with transaction() as c:
            current=c.execute('SELECT must_setup FROM users WHERE id=?',(row['id'],)).fetchone()
            if not current[0]:raise HTTPException(409,'Účet je už nastavený.')
            if c.execute('SELECT 1 FROM users WHERE email=? AND id!=?',(body.email,row['id'])).fetchone():raise HTTPException(409,'E-mail sa už používa.')
            c.execute('UPDATE users SET email=?,nickname=?,password_hash=?,must_setup=0 WHERE id=?',(body.email,body.nickname,encoded,row['id']))
            c.execute('DELETE FROM account_sessions WHERE user_id=?',(row['id'],));nonce=issue(c,row['id'],response)
            updated=c.execute('SELECT * FROM users WHERE id=?',(row['id'],)).fetchone()
        return {'user':public(updated),'csrf_token':nonce}
    @app.post('/api/auth/logout')
    def logout(request:Request,response:Response):
        row=get_session(request);csrf(request,row)
        with transaction() as c:c.execute('DELETE FROM account_sessions WHERE token_hash=?',(sha(request.cookies[COOKIE]),))
        response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='lax');return {'ok':True}
    @app.post('/api/auth/register',status_code=201)
    def register(body:Profile,request:Request,response:Response):
        origin(request)
        encoded=hasher.hash(body.password)
        with transaction() as c:
            if c.execute("SELECT value FROM auth_settings WHERE key='registration_enabled'").fetchone()[0]!='true':raise HTTPException(403,'Registrácia je vypnutá.')
            if c.execute('SELECT 1 FROM users WHERE email=?',(body.email,)).fetchone():raise HTTPException(409,'E-mail sa už používa.')
            identifier=str(uuid.uuid4());c.execute('INSERT INTO users VALUES(?,?,?,?,?,0)',(identifier,body.email,body.nickname,encoded,'user'))
            row=c.execute('SELECT * FROM users WHERE id=?',(identifier,)).fetchone()
            nonce=issue(c,identifier,response)
        return {'user':public(row),'csrf_token':nonce}
    @app.get('/api/auth/settings')
    def settings(request:Request):administrator(request);return config()
    @app.put('/api/auth/settings')
    def update_settings(body:Settings,request:Request):
        administrator(request)
        with transaction() as c:c.execute("UPDATE auth_settings SET value=? WHERE key='registration_enabled'",('true' if body.registration_enabled else 'false',))
        return {'registration_enabled':body.registration_enabled}
    return initialize,workspace,administrator
