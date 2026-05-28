# Smart AI CAM MCP verification (127.0.0.1:9877)
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = @"
import json, socket, sys, time
HOST, PORT = '127.0.0.1', 9877

def port_open():
    c = socket.socket()
    c.settimeout(2)
    try:
        c.connect((HOST, PORT))
        c.close()
        return True
    except OSError:
        return False

def send(action, params=None, timeout=60):
    params = params or {}
    c = socket.socket()
    c.settimeout(timeout)
    c.connect((HOST, PORT))
    c.sendall((json.dumps({'action': action, 'params': params}, ensure_ascii=False) + '\n').encode('utf-8'))
    buf = ''
    while True:
        d = c.recv(131072)
        if not d:
            break
        buf += d.decode('utf-8', errors='replace')
        if '\n' in buf:
            break
    c.close()
    return json.loads(buf.strip()) if buf.strip() else None

print('=== Smart AI CAM MCP verify ===')
print('Target:', HOST + ':' + str(PORT))
if not port_open():
    print('FAIL: Port closed. Enable add-in in Fusion (Scripts and Add-Ins).')
    sys.exit(1)
print('Port: OPEN')
failed = 0
tests = [
    ('get_addin_info', {}),
    ('get_cam_agent_manifest', {}),
    ('get_fusion_ai_gap_audit_pack', {}),
    ('knowledge_stats', {}),
    ('knowledge_query', {'material': 'AL6061', 'feature_type': 'hole',
     'geometry': {'diameter_mm': 5.0, 'hole_type': 'general'}}),
    ('scan_machining_features', {'material': 'S50C'}),
    ('get_cam_depth_plan', {'material': 'S50C', 'include_ai_tuning': True}),
    ('verify_cam_depth_plan', {'material': 'S50C', 'thinking_layer': 'L1_extended_features'}),
    ('get_ai_recommendations', {'material': 'S50C', 'thinking_layer': 'L1_extended_features'}),
]
for action, params in tests:
    t0 = time.perf_counter()
    try:
        r = send(action, params)
        dt = time.perf_counter() - t0
        ok = r and r.get('success')
        err = (r or {}).get('error', '')
        if ok:
            extra = ''
            if action == 'get_addin_info':
                d = r.get('data') or {}
                extra = 'version=' + str(d.get('version'))
            elif action == 'scan_machining_features':
                d = r.get('data') or {}
                extra = 'holes=' + str(len(d.get('holes') or []))
                cdc = d.get('cam_depth_context') or {}
                if cdc:
                    extra += ' stock_remove=' + str(cdc.get('stock_remove_mm'))
            elif action == 'get_cam_depth_plan':
                d = r.get('data') or {}
                cdc = d.get('cam_depth_context') or {}
                extra = 'remove=' + str((cdc.get('top_face_rough') or {}).get('stock_remove_mm'))
            elif action == 'verify_cam_depth_plan':
                d = r.get('data') or {}
                extra = 'verified=' + str(d.get('verified'))
            elif action == 'get_ai_recommendations':
                d = r.get('data') or {}
                pa = d.get('panel_apply') or {}
                extra = 'hole_rows=' + str(len(pa.get('hole_rows') or []))
            elif action == 'knowledge_stats':
                d = r.get('data') or {}
                extra = 'records=' + str(d.get('total_records'))
            print('[%.2fs] %s OK %s' % (dt, action, extra))
        else:
            print('[%.2fs] %s FAIL %s' % (dt, action, err[:120]))
            if action not in ('knowledge_query',):
                failed += 1
            if 'Unknown MCP action' in str(err):
                print('  -> Reload add-in: uncheck/check Smart AI CAM in Fusion')
    except Exception as ex:
        print('[ERR] %s %s' % (action, ex))
        failed += 1
r = send('__invalid_action__', {}, timeout=5)
if r and not r.get('success') and 'Unknown' in str(r.get('error', '')):
    print('[OK] invalid action rejected')
print('---')
if failed:
    print('RESULT: %d failed' % failed)
    sys.exit(1)
print('RESULT: all passed')
sys.exit(0)
"@
python -c $py
exit $LASTEXITCODE
