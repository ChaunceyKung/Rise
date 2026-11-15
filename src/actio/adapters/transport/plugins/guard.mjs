// Product guard/flush bridge. No model output, fault injection or predicted call IDs.
import { readFileSync } from 'node:fs'
import { canonical, hash, bytesHash, freeze, writer } from './common.mjs'
export const name = 'actio-guard'
export const inject = ['tools','sessionPersistence']
export async function apply(ctx, config) {
  const policy = freeze(JSON.parse(readFileSync(config.policy,'utf8')))
  const binding = freeze(config.binding), policyHash = hash(policy)
  const log = writer(config.spool, config.limits), used = new Map(), sessions = new Map()
  let budget = policy.maxCalls
  const active = () => JSON.parse(readFileSync(config.active,'utf8'))
  const bound = a => a.run === binding.run && a.epoch === binding.epoch && a.creation === binding.creation && a.session === binding.session && a.nonce === binding.nonce
  ctx.tools.guard(exec => {
    let reason, a, finalHash, schemas, schemaHash
    try {
      a = active()
      finalHash = hash({name:exec.name, arguments:exec.arguments})
      schemas = ctx.tools.schemas(exec.agent)
      schemaHash = hash(schemas)
      const key = binding.creation+':'+exec.callId, previous = used.get(key)
      if (!bound(a) || canonical(policy.binding) !== canonical(binding) || String(exec.agent?.session.id) !== binding.session) reason = 'binding mismatch'
      else if (Date.now() >= policy.expires) reason = 'policy expired'
      else if (schemaHash !== policy.registryHash) reason = 'registry/schema drift'
      else if (bytesHash(readFileSync(config.tool)) !== policy.toolHash) reason = 'tool artifact drift'
      else if (exec.name !== policy.tool || typeof exec.callId !== 'string' || !exec.callId) reason = 'unknown tool/call identity'
      else if (!exec.arguments || typeof exec.arguments !== 'object' || Array.isArray(exec.arguments) || Object.keys(exec.arguments).sort().join(',') !== 'key,op' || typeof exec.arguments.op !== 'string' || exec.arguments.op !== a.op || !policy.keys.includes(exec.arguments.key)) reason = 'final parameter scope'
      else if (previous) reason = previous === finalHash ? 'duplicate call' : 'call identity conflict'
      else if (budget <= 0) reason = 'budget exhausted'
      if (!reason) { used.set(key,finalHash); budget-- }
    } catch (e) { reason = 'invalid final request: '+String(e) }
    log({kind:'guard',...binding,op:a?.op ?? null,callId:exec.callId,finalHash:finalHash ?? null,policyHash,schemaHash:schemaHash ?? null,toolHash:policy.toolHash,allowed:!reason,reason:reason ?? null,remaining:budget})
    return reason
  })
  ctx.on('tools/result',(exec,result) => log({kind:'tool-result',...binding,op:active().op,callId:exec.callId,result}))
  ctx.on('session/event',(session,event) => {
    const a = active()
    if (!bound(a) || String(session.id) !== binding.session) throw new Error('unbound native event')
    let s = sessions.get(a.op)
    if (!s) { s = {through:-1,receipt:null,terminal:null}; sessions.set(a.op,s) }
    if (event.type === 'agent/inbox/spliced') {
      for (const m of event.data?.inserted ?? []) {
        if (m.source?.kind === 'user') s.receipt = m.id
      }
    }
    if (event.type === 'turn/end') s.terminal = {seq:event.seq,reason:event.data?.reason?.kind ?? null}
    s.through = event.seq
    log({kind:'observed',...binding,op:a.op,seq:event.seq,eventType:event.type})
  })
  ctx.on('agent/status',async ({agent,status}) => {
    if (status !== 'idle') return
    const a = active(), s = sessions.get(a.op)
    if (!bound(a) || String(agent.session.id) !== binding.session || !s?.receipt || !s.terminal) return
    // Snapshot before await: never label a later operation's prefix with an old receipt.
    const marker = {kind:'flush',...binding,op:a.op,...structuredClone(s)}
    await ctx.sessionPersistence.flush()
    log(marker)
  })
  log({kind:'guard-ready',...binding,policyHash,pid:process.pid})
}
