export type PrinterProfile = {
 id:string; name:string; printer_model:'p15'|'brother_ql810w';
 width_mm:number; length_mm:number; dpi:number; continuous:boolean;
};
export function MediaSettings({profiles,profileId,length,cut,model,busy,onProfile,onLength,onCut}:{
 profiles:PrinterProfile[];profileId:string;length:number;cut:boolean;model:string;busy:boolean;
 onProfile:(id:string)=>void;onLength:(length:number)=>void;onCut:(cut:boolean)=>void;
}){
 if(model!=='brother_ql810w')return null;
 const selected=profiles.find(p=>p.id===profileId);
 return <div className="media-settings">
  <label htmlFor="media-profile">Rolka / formát štítku</label>
  <select id="media-profile" value={profileId} onChange={e=>onProfile(e.target.value)} disabled={busy}>
   {profiles.filter(p=>p.printer_model===model).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
  </select>
  {selected?.continuous&&<><label htmlFor="media-length">Dĺžka štítku · mm</label>
   <input id="media-length" type="number" min={20} max={200} value={length}
    onChange={e=>onLength(Math.max(20,Math.min(200,Math.round(Number(e.target.value)||20))))} disabled={busy}/>
   <p className="small muted">20–200 mm. Zvolená šírka musí zodpovedať založenej rolke.</p></>}
  <label className="cut-option"><input type="checkbox" checked={cut} onChange={e=>onCut(e.target.checked)} disabled={busy}/> Automaticky odrezať štítok</label>
  <p className="small muted">Brother · čiernobiela tlač · 300 dpi</p>
 </div>;
}
export function mediaName(value?:string|null){
 if(!value)return 'Nedostupné';
 const match=value.match(/_(\d+)x(\d+)mm$/);
 if(!match)return 'Nerozpoznaná rolka';
 return Number(match[2])===0?match[1]+' mm · súvislá páska':match[1]+' × '+match[2]+' mm';
}
