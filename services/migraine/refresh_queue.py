"""Durable derivative work; canonical correction and enqueue share one transaction."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from time import monotonic
import threading
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from services.db import pg, _clean_dsn

class RefreshLeaseLost(RuntimeError): pass
class RefreshBudgetYield(RuntimeError): pass

async def enqueue(conn, user_id, episode_id, request_id, refresh_days, pattern_since_day):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("set local lock_timeout='2000ms'")
        await cur.execute('''insert into raw.migraine_time_refresh_users(user_id,generation)
            values(%s,1) on conflict(user_id) do update
            set generation=raw.migraine_time_refresh_users.generation+1,updated_at=clock_timestamp()
            returning generation''',(user_id,))
        generation=(await cur.fetchone())['generation']
        await cur.execute("update raw.migraine_time_refresh_jobs set status='pending',attempts=0,available_at=clock_timestamp(),last_error_class=null where user_id=%s and status='blocked'",(user_id,))
        await cur.execute('''insert into raw.migraine_time_refresh_jobs
            (user_id,request_id,episode_id,generation,refresh_days,pattern_since_day)
            values(%s,%s,%s,%s,%s::date[],%s::date)''',
            (user_id,str(request_id),episode_id,generation,refresh_days,pattern_since_day))

async def receipt_refresh(conn,user_id,request_id):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute('select status from raw.migraine_time_refresh_jobs where user_id=%s and request_id=%s',(user_id,str(request_id)))
        row=await cur.fetchone()
    if row is None: raise RuntimeError('Durable refresh receipt is missing')
    return {'status':'complete' if row['status']=='complete' else 'blocked' if row['status']=='blocked' else 'pending',
            'pending_components':[] if row['status']=='complete' else ['daily_gauges','personal_patterns']}

@contextmanager
def connection(dsn=None):
    with psycopg.connect(dsn or pg._dsn,row_factory=dict_row,connect_timeout=5,prepare_threshold=None) as conn:
        conn.execute("set local statement_timeout='10000ms'")
        conn.execute("set local lock_timeout='2000ms'")
        yield conn

def claim(*,dsn=None,lease_seconds=120,max_jobs=32):
    assert 5<=lease_seconds<=600 and 1<=max_jobs<=100
    with connection(dsn) as conn:
        user=conn.execute('''select u.user_id,u.generation,u.progress_generation,u.completed_days from raw.migraine_time_refresh_users u
            where (u.lease_until is null or u.lease_until<=clock_timestamp())
              and exists(select 1 from raw.migraine_time_refresh_jobs j where j.user_id=u.user_id
                and j.status in ('pending','running') and j.available_at<=clock_timestamp())
            order by u.updated_at,u.user_id for update of u skip locked limit 1''').fetchone()
        if not user:return None
        if user['progress_generation']!=user['generation']:
            conn.execute("update raw.migraine_time_refresh_jobs set attempts=0,available_at=clock_timestamp() where user_id=%s and status in ('pending','running')",(user['user_id'],))
        # A killed process cannot call retry(). Exhaust expired no-progress attempts here.
        conn.execute("""update raw.migraine_time_refresh_jobs set status='blocked',lease_token=null,
            last_error_class='WorkerProcessLost' where user_id=%s and status='running' and attempts>=5""",(user['user_id'],))
        ready=conn.execute("""select 1 from raw.migraine_time_refresh_jobs where user_id=%s
            and status in ('pending','running') and available_at<=clock_timestamp() limit 1""",(user['user_id'],)).fetchone()
        if not ready:
            conn.execute('update raw.migraine_time_refresh_users set lease_token=null,lease_until=null,updated_at=clock_timestamp() where user_id=%s',(user['user_id'],))
            return None
        token=uuid4()
        conn.execute('''update raw.migraine_time_refresh_users set lease_token=%s,
            lease_until=clock_timestamp()+(%s*interval '1 second'),writer_epoch=writer_epoch+1,
            progress_generation=generation,
            completed_days=case when progress_generation=generation then completed_days else '{}'::date[] end,
            updated_at=clock_timestamp() where user_id=%s''',(token,lease_seconds,user['user_id']))
        jobs=conn.execute('''select request_id,refresh_days,pattern_since_day from raw.migraine_time_refresh_jobs
            where user_id=%s and status in ('pending','running') and available_at<=clock_timestamp()
            order by generation,request_id limit %s for update''',(user['user_id'],max_jobs)).fetchall()
        ids=[j['request_id'] for j in jobs]
        conn.execute('''update raw.migraine_time_refresh_jobs set status='running',attempts=attempts+1,
            lease_token=%s,last_error_class=null where user_id=%s and request_id=any(%s::uuid[])''',
            (token,user['user_id'],ids))
    return {'user_id':str(user['user_id']),'generation':user['generation'],'lease_token':str(token),
            'completed_days':user['completed_days'] if user['progress_generation']==user['generation'] else [],
            'request_ids':[str(x) for x in ids], 'refresh_days':sorted({d for j in jobs for d in j['refresh_days']}),
            'pattern_since_day':min(j['pattern_since_day'] for j in jobs)}

def renew(batch,*,dsn=None,lease_seconds=120):
    with connection(dsn) as conn:
        row=conn.execute('''update raw.migraine_time_refresh_users
            set lease_until=clock_timestamp()+(%s*interval '1 second')
            where user_id=%s and generation=%s and lease_token=%s and lease_until>clock_timestamp()
            returning user_id''',(lease_seconds,batch['user_id'],batch['generation'],batch['lease_token'])).fetchone()
        if not row:raise RefreshLeaseLost('refresh ownership changed')

def mark_day(batch,day,*,dsn=None):
    with connection(dsn) as conn:
        row=conn.execute("""update raw.migraine_time_refresh_users set completed_days=
            case when %s=any(completed_days) then completed_days else array_append(completed_days,%s::date) end
            where user_id=%s and generation=%s and progress_generation=%s and lease_token=%s
              and lease_until>clock_timestamp() returning user_id""",
            (day,day,batch['user_id'],batch['generation'],batch['generation'],batch['lease_token'])).fetchone()
        if not row:raise RefreshLeaseLost('refresh ownership changed')
        conn.execute("update raw.migraine_time_refresh_jobs set attempts=0 where user_id=%s and request_id=any(%s::uuid[]) and status='running' and lease_token=%s",(batch['user_id'],batch['request_ids'],batch['lease_token']))


def complete(batch,*,dsn=None):
    with connection(dsn) as conn:
        row=conn.execute('''select generation,lease_token,lease_until>clock_timestamp() as live
            from raw.migraine_time_refresh_users where user_id=%s for update''',(batch['user_id'],)).fetchone()
        if not row or row['generation']!=batch['generation'] or str(row['lease_token'])!=batch['lease_token'] or not row['live']:
            raise RefreshLeaseLost('refresh ownership changed')
        conn.execute('''update raw.migraine_time_refresh_jobs set status='complete',completed_at=clock_timestamp(),
            lease_token=null,last_error_class=null where user_id=%s and request_id=any(%s::uuid[])
            and status='running' and lease_token=%s''',(batch['user_id'],batch['request_ids'],batch['lease_token']))
        conn.execute('''update raw.migraine_time_refresh_users set lease_token=null,lease_until=null,
            updated_at=clock_timestamp() where user_id=%s''',(batch['user_id'],))

def retry(batch,error,*,dsn=None):
    # No message/SQL/payload is persisted, only bounded exception class.
    error_class=type(error).__name__[:80]
    with connection(dsn) as conn:
        state=conn.execute('select lease_token,generation from raw.migraine_time_refresh_users where user_id=%s for update',(batch['user_id'],)).fetchone()
        if not state or str(state['lease_token'])!=batch['lease_token']:return False
        requeue=state['generation']!=batch['generation'] or isinstance(error,RefreshBudgetYield)
        conn.execute('''update raw.migraine_time_refresh_jobs set status=case when attempts>=5 and not %s then 'blocked' else 'pending' end,lease_token=null,
            attempts=case when %s then 0 else attempts end,
            last_error_class=%s,available_at=clock_timestamp()+
              (case when %s then 0 else least(300,5*power(2,least(attempts,6))) end *interval '1 second')
            where user_id=%s and request_id=any(%s::uuid[]) and status='running' and lease_token=%s''',
            (requeue,requeue,error_class,requeue,batch['user_id'],batch['request_ids'],batch['lease_token']))
        conn.execute('update raw.migraine_time_refresh_users set lease_token=null,lease_until=null,updated_at=clock_timestamp() where user_id=%s',(batch['user_id'],))
    return True

class LeaseKeeper:
    """Renew independently of slow compute; loss/deadline revokes completion authority."""
    def __init__(self,batch,*,dsn=None,lease_seconds=120,hard_seconds=240):
        self.batch=batch;self.dsn=dsn;self.lease_seconds=lease_seconds;self.hard_seconds=hard_seconds
        self.stop=threading.Event();self.error=None;self.started=monotonic();self.thread=None
    def check(self):
        if self.error is not None:raise self.error
        if monotonic()-self.started>=self.hard_seconds:raise TimeoutError('refresh execution deadline')
    def _run(self):
        interval=min(20.0,self.lease_seconds/3)
        while not self.stop.wait(min(interval,max(.01,self.hard_seconds-(monotonic()-self.started)))):
            try:
                self.check()
                while True:
                    self.check()
                    try:
                        renew(self.batch,dsn=self.dsn,lease_seconds=self.lease_seconds)
                        break
                    except psycopg.errors.LockNotAvailable:
                        # Our own atomic publication may hold this row. Retry only;
                        # renew still refuses expired or superseded authority.
                        if self.stop.wait(.1):return
            except Exception as exc:
                self.error=exc
                try:retry(self.batch,exc,dsn=self.dsn)
                except Exception:pass  # Database lease still expires; never claim completion.
                return
    def __enter__(self):
        self.thread=threading.Thread(target=self._run,name='migraine-refresh-lease',daemon=True)
        self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join(timeout=16)
        if self.thread.is_alive():raise RefreshLeaseLost('lease renewal did not stop')

def health(*,dsn=None):
    with connection(dsn) as conn:
        return dict(conn.execute("""select count(*) filter(where status='blocked') as blocked_jobs,
            count(*) filter(where status in ('pending','running')) as pending_jobs
            from raw.migraine_time_refresh_jobs""").fetchone())


def process(batch,*,dsn=None,lease_seconds=120,max_seconds=90,hard_seconds=240):
    from services.migraine.refresh_publication import worker_publication
    from bots.gauges.gauge_scorer import score_user_day
    from bots.patterns.pattern_engine_job import run_pattern_engine
    if dsn is not None and _clean_dsn(dsn)!=pg._dsn:
        raise ValueError('queue and derivative database must match')
    assert 1<=hard_seconds<=240
    began=monotonic()
    def checkpoint():
        if monotonic()-began>max_seconds:raise RefreshBudgetYield('refresh batch budget')
        renew(batch,dsn=dsn,lease_seconds=lease_seconds)
    try:
        keeper=LeaseKeeper(batch,dsn=dsn,lease_seconds=lease_seconds,hard_seconds=hard_seconds)
        with keeper,worker_publication(batch['user_id'],batch['generation'],batch['lease_token']):
            for day in batch['refresh_days']:
                if day in batch.get('completed_days',[]):continue
                keeper.check();checkpoint()
                with pg.operation_timeouts(connect_timeout=5,statement_timeout_ms=10000),pg.connection_scope():
                    score_user_day(batch['user_id'],day,force=True,require_corrected_symptoms=True)
                mark_day(batch,day,dsn=dsn)
            keeper.check();checkpoint()
            today=datetime.now(timezone.utc).date()
            run_pattern_engine(as_of_day=today,days_back=(today-batch['pattern_since_day']).days+1,
                user_id=batch['user_id'],require_corrected_symptoms=True,dsn=pg._dsn)
            keeper.check()
        # No renewal thread may race clearing a completed lease.
        keeper.check();complete(batch,dsn=dsn)
        return True
    except Exception as exc:
        retry(batch,exc,dsn=dsn)
        return False
