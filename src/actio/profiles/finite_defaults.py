"""Shared finite-task persona and bounded deadline contract."""
PERSONA='You are one actor in a finite synthetic task. Follow the public rules and your own hard constraints. Use only your own context and actual public actions. Return exactly one action_spec option as plain text without quotes, JSON, explanation or private details.'
TIMEOUTS={'ready':30,'rpc':5,'first_response':60,'idle':60,'request':90,'result':115,'drained':5,'closed':5,'worker':165}
DEADLINES={
 'ready':'supervisor wait after Worker launch; SDK initialize=20 within ready=30',
 'rpc':'SDK RPC each=5; submit acknowledgement, not whole generation',
 'headers':'final fetch start; 60s; official idle also runs before headers',
 'idle':'official adapter stream start/reset on adapter activity; 60s including preheaders',
 'total':'official adapter request and final fetch have independent 90s deadlines; earlier wins; heartbeats cannot extend total',
 'result':'supervisor wait after submit send; 115s includes RPC/generation/terminal; contains 90s request plus bounded local overhead',
 'drain':'after result, 5s', 'close':'after domain effect, 5s',
 'worker':'supervisor start, 165s; 30+115+5+5=155 leaves 10s margin; startup/overhead may trigger earlier outer bound',
 'cleanup':'Job termination; no semantic cancel or recovery guarantee'}
