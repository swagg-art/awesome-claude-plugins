"""SMA crossover backtest (fast=31, slow=50) on daily bars from Yahoo Finance.
Signal computed on close, position taken next day's open (no lookahead). Cost 0.05% per side.
Usage: python sma_cross_backtest.py QQQ SPY DIA"""
import sys, json, urllib.request, numpy as np, pandas as pd
def get(sym, rng="10y"):
    u=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range={rng}"
    r=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30))["chart"]["result"][0]
    q=r["indicators"]["quote"][0]
    return pd.DataFrame({"open":q["open"],"close":q["close"]},index=pd.to_datetime(r["timestamp"],unit="s").normalize()).dropna()
def stats(ret,name):
    eq=(1+ret).cumprod(); yrs=len(ret)/252; dd=(eq/eq.cummax()-1).min()
    sh=ret.mean()/ret.std()*np.sqrt(252) if ret.std()>0 else 0
    return f"{name:<22} total {eq.iloc[-1]-1:+8.1%}  CAGR {eq.iloc[-1]**(1/yrs)-1:+6.1%}  maxDD {dd:6.1%}  Sharpe {sh:4.2f}"
def backtest(df,fast=31,slow=50,cost=0.0005,short=False):
    sig=(df.close.rolling(fast).mean()>df.close.rolling(slow).mean()).astype(int)
    pos=(sig if not short else sig*2-1).shift(1).fillna(0)   # act next bar
    # position held open->open; approximate daily return close-to-close with entry at open on change days
    cc=df.close.pct_change().fillna(0); oc=(df.close/df.open-1)
    prev=pos.shift(1).fillna(0); chg=pos!=prev
    ret=np.where(chg, prev*(df.open/df.close.shift(1)-1).fillna(0)+pos*oc, pos*cc)
    ret=pd.Series(ret,index=df.index)-cost*(pos-prev).abs()
    return ret,int(chg.sum())
if __name__=="__main__":
    for s in sys.argv[1:] or ["QQQ","SPY","DIA"]:
        df=get(s); print(f"\n{s}  {df.index[0].date()} -> {df.index[-1].date()} ({len(df)} days)")
        bh=df.close.pct_change().fillna(0); print(stats(bh,"Buy & hold"))
        r,n=backtest(df); print(stats(r,"SMA31/50 long-only"), f"trades={n}")
        r,n=backtest(df,short=True); print(stats(r,"SMA31/50 long/short"), f"trades={n}")
