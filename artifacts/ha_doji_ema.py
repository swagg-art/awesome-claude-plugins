"""Strategy #7 (literal guess): Heikin Ashi + 100 EMA + doji trigger on 5-min bars.
Long: HA doji while HA close > EMA100 (and prior HA candle green) -> enter next bar open, stop = doji low.
Short mirrored. Target = rr * risk. Flat by 15:55 ET. Cost 0.05R/trade. Doji = HA body <= 25% of HA range.
Usage: python ha_doji_ema.py QQQ.csv"""
import sys, pandas as pd
def run(df, rr, cost=0.05, doji=0.25):
    c=(df.open+df.high+df.low+df.close)/4
    o=c.copy(); o.iloc[0]=(df.open.iloc[0]+df.close.iloc[0])/2
    for i in range(1,len(df)): o.iloc[i]=(o.iloc[i-1]+c.iloc[i-1])/2
    h=pd.concat([df.high,o,c],axis=1).max(axis=1); l=pd.concat([df.low,o,c],axis=1).min(axis=1)
    ema=c.ewm(span=100,adjust=False).mean(); body=(c-o).abs(); rng=(h-l).replace(0,float('nan'))
    res=[]; i=100; n=len(df)
    while i<n-2:
        if body.iloc[i]/rng.iloc[i]<=doji and df.index[i].time()<pd.Timestamp('15:30').time() and df.index[i].date()==df.index[i+1].date():
            side=1 if c.iloc[i]>ema.iloc[i] and c.iloc[i-1]>o.iloc[i-1] else -1 if c.iloc[i]<ema.iloc[i] and c.iloc[i-1]<o.iloc[i-1] else 0
            if side:
                e=df.open.iloc[i+1]; s=h.iloc[i] if side<0 else l.iloc[i]
                risk=abs(e-s)
                if risk>0:
                    tgt=e+side*rr*risk; out=None; j=i+1
                    while j<n and df.index[j].date()==df.index[i].date():
                        hi,lo=df.high.iloc[j],df.low.iloc[j]
                        if (side==1 and lo<=s) or (side==-1 and hi>=s): out=-1;break
                        if (side==1 and hi>=tgt) or (side==-1 and lo<=tgt): out=rr;break
                        if df.index[j].time()>=pd.Timestamp('15:55').time(): out=side*(df.close.iloc[j]-e)/risk;break
                        j+=1
                    if out is None: out=side*(df.close.iloc[j-1]-e)/risk
                    res.append(out-cost); i=j
        i+=1
    return pd.Series(res,dtype=float)
if __name__=="__main__":
    df=pd.read_csv(sys.argv[1],parse_dates=['timestamp']).set_index('timestamp')
    for rr in (0.5,1,2):
        r=run(df,rr); print(f"rr={rr}: n={len(r)} win={(r>0).mean():.0%} R={r.sum():+.1f}")
