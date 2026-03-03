"""Script to inject Supabase Realtime subscription code into index.html and monitor.html"""

SUPABASE_SCRIPT = """
<!-- Supabase Realtime: DB 변경을 브라우저가 직접 감지하여 자동 새로고침 -->
<script>
(function() {
    var SUPABASE_URL = 'https://kbnszmnmvppfbdpdefqw.supabase.co';
    var SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtibnN6bW5tdnBwZmJkcGRlZnF3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIwNzU2MDgsImV4cCI6MjA4NzY1MTYwOH0.nFTpkNsG5Wk3Q10khoAYNyA0UaKpP2kmHLoE5LsVh4A';
    window._gameIsActive = false;
    var _reloadTimer = null;
    function _scheduleReload() {
        if (window._gameIsActive) { console.log('[Supabase RT] 게임 중, 새로고침 대기'); return; }
        if (_reloadTimer) return;
        console.log('[Supabase RT] 데이터 변경 감지 -> 1초 후 자동 새로고침');
        _reloadTimer = setTimeout(function() { window.location.reload(); }, 1000);
    }
    try {
        var sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
        sb.channel('roulette-rt')
            .on('postgres_changes', {event: '*', schema: 'public', table: 'participants'}, function(p) {
                console.log('[Supabase RT] participants 변경:', p.eventType);
                _scheduleReload();
            })
            .on('postgres_changes', {event: '*', schema: 'public', table: 'commenters'}, function(p) {
                console.log('[Supabase RT] commenters 변경:', p.eventType);
                _scheduleReload();
            })
            .subscribe(function(status) {
                console.log('[Supabase RT] 구독 상태:', status);
            });
        console.log('[Supabase RT] Realtime 구독 초기화 완료');
    } catch(e) { console.error('[Supabase RT] 오류:', e); }
})();
</script>
"""

SUPABASE_CDN = '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>'

def inject_realtime(filepath, is_monitor=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove existing injection to avoid duplicates
    if 'roulette-rt' in content:
        print(f'{filepath}: Supabase RT already injected, skipping.')
        return

    # Inject before </body>
    if '</body>' in content:
        content = content.replace('</body>', SUPABASE_SCRIPT + '</body>', 1)
        print(f'{filepath}: Injected Supabase Realtime before </body>')
    else:
        content += SUPABASE_SCRIPT
        print(f'{filepath}: Appended Supabase Realtime at end')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

inject_realtime('f:/roulette-1/templates/index.html')
inject_realtime('f:/roulette-1/templates/monitor.html', is_monitor=True)
print('Done!')
