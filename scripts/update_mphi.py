#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re, sys
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs'/'data'/'latest.json'
URL='https://portodemanaus.com.br/nivel-do-rio-negro/'
TZ=timezone(timedelta(hours=-4))

def avg(xs,n):
    ys=[x['delta_cm'] for x in xs[-n:] if x.get('delta_cm') is not None]
    return round(sum(ys)/len(ys),2) if ys else None

def load():
    return json.loads(DATA.read_text(encoding='utf-8'))

def save(d):
    DATA.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')

def extract_latest(html):
    soup=BeautifulSoup(html,'html.parser')
    candidates=[]
    for t in soup.find_all('table'):
        text=' '.join(t.stripped_strings)
        if 'Cota' not in text or 'Dia' not in text:
            continue
        rows=[]
        for tr in t.find_all('tr'):
            cells=[c.get_text(' ',strip=True).replace(',','.') for c in tr.find_all(['td','th'])]
            if len(cells)<2:
                continue
            try:
                day=int(re.sub(r'\D','',cells[0]))
                level=float(re.search(r'\d+(?:\.\d+)?',cells[1]).group())
                delta=float(re.search(r'-?\d+(?:\.\d+)?',cells[2]).group()) if len(cells)>2 and re.search(r'-?\d',cells[2]) else None
                if 1<=day<=31 and 5<=level<=35:
                    rows.append((day,level,delta))
            except Exception:
                pass
        if rows:
            candidates.append(rows)
    if not candidates:
        raise RuntimeError('Nenhuma tabela mensal reconhecida')
    now=datetime.now(TZ)
    day,level,delta=candidates[0][-1]
    return f'{now.year:04d}-{now.month:02d}-{day:02d}',level,delta

def base_score_for_prefix(valid, idx, d):
    sub=valid[:idx+1]
    cur=sub[-1]
    level=cur['level']
    a7=avg(sub,7)
    a15=avg(sub,15)
    accel=round(a7-a15,2)
    sea=d.get('seasonal',{}).get(cur['date'][5:7])
    seasonal=2 if sea and level<sea['q1'] else 1 if sea and level<sea['median'] else 0
    vel=2 if a7<=-12 else 1 if a7<=-8 else 0
    acc=2 if accel<=-2 else 1 if accel<=-.5 else 0
    peak=max(x['level'] for x in sub)
    pk=d['june_peak_reference']
    peakpts=2 if peak<pk['q1'] else 1 if peak<pk['median'] else 0
    drawdown=peak-level
    dd=2 if drawdown>=4 else 1 if drawdown>=3 else 0
    return seasonal+vel+acc+peakpts+dd

def persistence_days(valid,d):
    count=0
    later_date=None
    for i in range(len(valid)-1,-1,-1):
        current_date=datetime.fromisoformat(valid[i]['date']).date()
        if later_date is not None and (later_date-current_date).days != 1:
            break
        if base_score_for_prefix(valid,i,d) < 3:
            break
        count += 1
        later_date=current_date
    return count

def recalc(d):
    s=sorted(d['series'],key=lambda x:x['date'])
    valid=[x for x in s if x.get('level') is not None]
    c=d['current']
    last=valid[-1]
    c.update(date=last['date'],level=last['level'],delta_cm=last.get('delta_cm'))
    c['avg3']=avg(valid,3)
    c['avg7']=avg(valid,7)
    c['avg15']=avg(valid,15)
    c['avg30']=avg(valid,30)
    c['accel_7_15']=round(c['avg7']-c['avg15'],2)
    peak=max(x['level'] for x in valid)
    peakrow=min((x for x in valid if x['level']==peak),key=lambda x:x['date'])
    c['peak']=peak
    c['peak_date']=peakrow['date']
    c['drawdown']=round(peak-c['level'],2)
    c['phase']='Vazante' if c['avg3']<-0.5 else 'Enchente' if c['avg3']>0.5 else 'Estabilidade'
    base=base_score_for_prefix(valid,len(valid)-1,d)
    c['base_score']=base
    c['persistence_days']=persistence_days(valid,d)
    c['persistence_points']=2 if c['persistence_days']>=7 else 0
    c['score']=base+c['persistence_points']
    c['status']='NORMAL' if c['score']<=2 else 'ATENÇÃO' if c['score']<=6 else 'ALTO'
    rates={'soft':c['avg30'],'central':(c['avg7']+c['avg15'])/2,'stress':min(c['avg3'],c['avg7'],c['avg15'])}
    conf={7:'Média',15:'Média-baixa',30:'Baixa'}
    d['projections']={str(days):{**{k:round(c['level']+r*days/100,2) for k,r in rates.items()},'confidence':conf[days]} for days in (7,15,30)}
    d['meta']['updated_at']=datetime.now(TZ).isoformat(timespec='seconds')
    d['meta']['source_status']='ok'
    d['meta']['last_score_date']=c['date']
    d['series']=s

def main():
    d=load()
    try:
        r=requests.get(URL,timeout=30,headers={'User-Agent':'MPHI-Uiara/1.0'})
        r.raise_for_status()
        date,level,delta=extract_latest(r.text)
        prev=next((x for x in reversed(d['series']) if x.get('level') is not None),None)
        if prev and date>prev['date'] and abs(level-prev['level'])>1.0:
            raise RuntimeError(f'Salto anômalo: {prev["level"]} -> {level} m')
        found=next((x for x in d['series'] if x['date']==date),None)
        if found:
            found.update(level=level,delta_cm=delta,source='Porto de Manaus')
        else:
            d['series'].append({'date':date,'level':level,'delta_cm':delta,'source':'Porto de Manaus'})
        recalc(d)
        d['meta']['source_note']='Atualização automática concluída a partir do Porto de Manaus.'
        save(d)
    except Exception as e:
        d['meta']['source_status']='stale'
        d['meta']['source_note']='FONTE NÃO ATUALIZADA: '+str(e)
        d['meta']['updated_at']=datetime.now(TZ).isoformat(timespec='seconds')
        save(d)
        print(e,file=sys.stderr)
        sys.exit(2)

if __name__=='__main__':
    main()
