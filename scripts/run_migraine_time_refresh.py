#!/usr/bin/env python3
"""Bounded cron drain. Work survives crashes; runtime feature flag is independent."""
import argparse,json,os,time
from services.migraine.refresh_queue import claim,process,health,retry,RefreshBudgetYield

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--max-users',type=int,default=4)
    parser.add_argument('--max-seconds',type=int,default=240)
    args=parser.parse_args()
    if not 1<=args.max_users<=20 or not 10<=args.max_seconds<=600:parser.error('bounds exceeded')
    if os.getenv('GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED','0')!='1':
        print(json.dumps({'status':'disabled'}));return
    start=time.monotonic();done=failed=0
    while done+failed<args.max_users and time.monotonic()-start<args.max_seconds:
        remaining=args.max_seconds-(time.monotonic()-start)
        if remaining<1:break
        batch=claim()
        if batch is None:break
        remaining=args.max_seconds-(time.monotonic()-start)
        if remaining<1:
            retry(batch,RefreshBudgetYield());break
        if process(batch,max_seconds=min(90,remaining),hard_seconds=min(240,remaining)):done+=1
        else:failed+=1
    state=health()
    print(json.dumps({'completed_batches':done,'pending_batches':failed,**state}))
    if failed or state['blocked_jobs']:raise SystemExit(1)
if __name__=='__main__':main()
