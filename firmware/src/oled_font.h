#pragma once
#include <cstdint>
// Original project 5x7 glyphs, shared with api/pixel_font.py.
namespace FpsOled {
inline const uint8_t* glyph(char c){
  if(c>='a'&&c<='z')c-=32;
  switch(c){
    case ' ': {static const uint8_t rows[7]={0,0,0,0,0,0,0};return rows;}
    case '!': {static const uint8_t rows[7]={4,4,4,4,4,0,4};return rows;}
    case '"': {static const uint8_t rows[7]={10,10,10,0,0,0,0};return rows;}
    case '#': {static const uint8_t rows[7]={10,10,31,10,31,10,10};return rows;}
    case '%': {static const uint8_t rows[7]={17,2,4,8,16,17,0};return rows;}
    case '&': {static const uint8_t rows[7]={12,18,20,8,21,18,13};return rows;}
    case '\'': {static const uint8_t rows[7]={4,4,8,0,0,0,0};return rows;}
    case '(': {static const uint8_t rows[7]={2,4,8,8,8,4,2};return rows;}
    case ')': {static const uint8_t rows[7]={8,4,2,2,2,4,8};return rows;}
    case '*': {static const uint8_t rows[7]={0,21,14,31,14,21,0};return rows;}
    case '+': {static const uint8_t rows[7]={0,4,4,31,4,4,0};return rows;}
    case ',': {static const uint8_t rows[7]={0,0,0,0,4,4,8};return rows;}
    case '-': {static const uint8_t rows[7]={0,0,0,31,0,0,0};return rows;}
    case '.': {static const uint8_t rows[7]={0,0,0,0,0,12,12};return rows;}
    case '/': {static const uint8_t rows[7]={1,2,2,4,8,8,16};return rows;}
    case '0': {static const uint8_t rows[7]={14,17,19,21,25,17,14};return rows;}
    case '1': {static const uint8_t rows[7]={4,12,4,4,4,4,14};return rows;}
    case '2': {static const uint8_t rows[7]={14,17,1,2,4,8,31};return rows;}
    case '3': {static const uint8_t rows[7]={30,1,1,14,1,1,30};return rows;}
    case '4': {static const uint8_t rows[7]={2,6,10,18,31,2,2};return rows;}
    case '5': {static const uint8_t rows[7]={31,16,16,30,1,1,30};return rows;}
    case '6': {static const uint8_t rows[7]={14,16,16,30,17,17,14};return rows;}
    case '7': {static const uint8_t rows[7]={31,1,2,4,8,8,8};return rows;}
    case '8': {static const uint8_t rows[7]={14,17,17,14,17,17,14};return rows;}
    case '9': {static const uint8_t rows[7]={14,17,17,15,1,1,14};return rows;}
    case ':': {static const uint8_t rows[7]={0,12,12,0,12,12,0};return rows;}
    case ';': {static const uint8_t rows[7]={0,12,12,0,4,4,8};return rows;}
    case '<': {static const uint8_t rows[7]={1,2,4,8,4,2,1};return rows;}
    case '=': {static const uint8_t rows[7]={0,31,0,31,0,0,0};return rows;}
    case '>': {static const uint8_t rows[7]={16,8,4,2,4,8,16};return rows;}
    case '?': {static const uint8_t rows[7]={14,17,1,2,4,0,4};return rows;}
    case '@': {static const uint8_t rows[7]={14,17,23,21,23,16,14};return rows;}
    case 'A': {static const uint8_t rows[7]={14,17,17,31,17,17,17};return rows;}
    case 'B': {static const uint8_t rows[7]={30,17,17,30,17,17,30};return rows;}
    case 'C': {static const uint8_t rows[7]={14,17,16,16,16,17,14};return rows;}
    case 'D': {static const uint8_t rows[7]={30,17,17,17,17,17,30};return rows;}
    case 'E': {static const uint8_t rows[7]={31,16,16,30,16,16,31};return rows;}
    case 'F': {static const uint8_t rows[7]={31,16,16,30,16,16,16};return rows;}
    case 'G': {static const uint8_t rows[7]={14,17,16,23,17,17,15};return rows;}
    case 'H': {static const uint8_t rows[7]={17,17,17,31,17,17,17};return rows;}
    case 'I': {static const uint8_t rows[7]={31,4,4,4,4,4,31};return rows;}
    case 'J': {static const uint8_t rows[7]={7,2,2,2,18,18,12};return rows;}
    case 'K': {static const uint8_t rows[7]={17,18,20,24,20,18,17};return rows;}
    case 'L': {static const uint8_t rows[7]={16,16,16,16,16,16,31};return rows;}
    case 'M': {static const uint8_t rows[7]={17,27,21,21,17,17,17};return rows;}
    case 'N': {static const uint8_t rows[7]={17,25,21,19,17,17,17};return rows;}
    case 'O': {static const uint8_t rows[7]={14,17,17,17,17,17,14};return rows;}
    case 'P': {static const uint8_t rows[7]={30,17,17,30,16,16,16};return rows;}
    case 'Q': {static const uint8_t rows[7]={14,17,17,17,21,18,13};return rows;}
    case 'R': {static const uint8_t rows[7]={30,17,17,30,20,18,17};return rows;}
    case 'S': {static const uint8_t rows[7]={15,16,16,14,1,1,30};return rows;}
    case 'T': {static const uint8_t rows[7]={31,4,4,4,4,4,4};return rows;}
    case 'U': {static const uint8_t rows[7]={17,17,17,17,17,17,14};return rows;}
    case 'V': {static const uint8_t rows[7]={17,17,17,17,17,10,4};return rows;}
    case 'W': {static const uint8_t rows[7]={17,17,17,21,21,27,17};return rows;}
    case 'X': {static const uint8_t rows[7]={17,17,10,4,10,17,17};return rows;}
    case 'Y': {static const uint8_t rows[7]={17,17,10,4,4,4,4};return rows;}
    case 'Z': {static const uint8_t rows[7]={31,1,2,4,8,16,31};return rows;}
    case '[': {static const uint8_t rows[7]={14,8,8,8,8,8,14};return rows;}
    case '\\': {static const uint8_t rows[7]={16,8,8,4,2,2,1};return rows;}
    case ']': {static const uint8_t rows[7]={14,2,2,2,2,2,14};return rows;}
    case '_': {static const uint8_t rows[7]={0,0,0,0,0,0,31};return rows;}
    case '|': {static const uint8_t rows[7]={4,4,4,4,4,4,4};return rows;}
    default: {static const uint8_t rows[7]={14,17,1,2,4,0,4};return rows;}
  }
}
}
