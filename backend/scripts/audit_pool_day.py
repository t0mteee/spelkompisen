"""Read-only audit of frozen pool selections; never rebuilds or changes a coupon.

Run on the server: PYTHONPATH=. .venv/bin/python scripts/audit_pool_day.py
    data/stryktips.db --product stryktipset --draw 4969
"""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from app.pool_system_ledger import system_detail, _decode_rows


def audit(conn, product, draw):
    keys = conn.execute(
        "SELECT horizon, config_key FROM pool_system_ledger "
        "WHERE product=? AND draw_number=? AND budget>=5000 "
        "ORDER BY horizon, config_key", (product, draw)).fetchall()
    systems = []
    for horizon, key in keys:
        d = system_detail(SimpleNamespace(conn=conn), product, draw, horizon, key)
        events = d['events']
        ceiling = sum(e['outcome'] in e['covered'] for e in events)
        systems.append({
            'horizon': horizon, 'config': key, 'rows': d['n_rows'],
            'best': d['correct_max'], 'cost': d['cost_kr'],
            'payout': d['payout_kr'], 'roi': d['roi'],
            'coverage_ceiling': ceiling,
            'reduction_loss': ceiling - d['correct_max'] if d['correct_max'] is not None else None,
            'events': [{
                'n': e['event_number'], 'match': e['description'],
                'outcome': e['outcome'], 'covered': ''.join(e['covered']),
                'result_share': round(e['sign_shares'].get(e['outcome'], 0), 4),
                'shares': e['sign_shares'], 'sharp': e['sharp_odds_at_freeze'],
                'svs': e['odds_at_freeze'], 'streck': e['streck_at_freeze'],
                'total': e['total_at_freeze'],
            } for e in events],
        })
    # Aggregate only same-version, same-draw, same-horizon complete PH5 pairs.
    records = conn.execute(
        "SELECT product,draw_number,horizon,config_key,cost_kr,payout_kr,correct_max "
        "FROM pool_system_ledger WHERE config_key LIKE 'ph5-v4-%' "
        "AND timely=1 AND payout_complete=1 AND roi IS NOT NULL "
        "AND frozen_at <= (SELECT MAX(frozen_at) FROM pool_system_ledger "
        "WHERE product=? AND draw_number=?)", (product, draw)).fetchall()
    paired = defaultdict(dict)
    for p, n, h, k, cost, payout, best in records:
        paired[(p, n, h)][k.rsplit('-', 1)[-1]] = (cost, payout, best)
    totals = defaultdict(Counter)
    for (p, n, h), methods in paired.items():
        if not {'medel', 'maxev', 'favoritrad', 'byggarslump'} <= methods.keys():
            continue
        for method, (cost, payout, best) in methods.items():
            t = totals[(p, h, method)]
            t.update(n=1, cost=cost, payout=payout, top_hits=int(best == (13 if p in ('stryktipset', 'europatipset') else 8)))
    played = []
    outcomes = dict(conn.execute(
        'SELECT event_number,outcome FROM pool_event_settlement WHERE product=? AND draw_number=?',
        (product, draw)))
    for id_, label, cost, best, payout, order, text in conn.execute(
            'SELECT id,label,cost_kr,correct_max,payout_kr,events_order,rows_text '
            'FROM pool_played_coupon WHERE product=? AND draw_number=?', (product, draw)):
        order = json.loads(order)
        rows = _decode_rows(text)
        missing = [event for index, event in enumerate(order)
                   if not any(row[index] == outcomes.get(event) for row in rows)]
        played.append(dict(id=id_, label=label, cost=cost, best=best, payout=payout,
                           missing_events=missing,
                           reduction_loss=len(order)-len(missing)-best if best is not None else None))
    return {'product': product, 'draw': draw, 'systems': systems, 'played': played,
            'paired_history': [dict(product=p, horizon=h, method=m, **t,
                roi=t['payout']/t['cost']-1) for (p,h,m), t in sorted(totals.items())]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('--product', default='stryktipset')
    parser.add_argument('--draw', type=int, required=True)
    args = parser.parse_args()
    with sqlite3.connect(Path(args.database).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.execute('PRAGMA query_only=ON')
        print(json.dumps(audit(conn, args.product, args.draw), ensure_ascii=False, indent=2))
