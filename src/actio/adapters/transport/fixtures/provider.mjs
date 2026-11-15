// Deterministic model fixture only. DSH owns the loop and all tool execution.
import { writer } from '../plugins/common.mjs'
export const name = 'actio-fixture-provider'
export const inject = ['llm']
export function apply(ctx, config) {
  const log = writer(config.capture, config.limits), calls = new Map()
  class Fixture {
    providerInfo(provider) { return {id:provider,name:provider} }
    providerRetryPolicy() { return undefined }
    imageRequestPricing() { return undefined }
    async listModels() { return [] }
    async resolveModel(provider,model) { return {provider,id:model,name:model,context:{contextWindow:32000}} }
    async prepareCall(provider,model) { return {model:await this.resolveModel(provider,model),stream:o=>this.stream(o)} }
    async *stream(options) {
      const prompt = options.messages.findLast(m=>m.role==='user' && m.source?.kind==='user')
      const task = JSON.parse(prompt.content.filter(b=>b.type==='text').map(b=>b.text).join(''))
      const count = (calls.get(task.op) ?? 0)+1
      calls.set(task.op,count)
      if (count > 4) throw new Error('fixture request bound exceeded')
      log({kind:'provider-input',op:task.op,messages:options.messages})
      const already = options.messages.some(m=>m.source?.kind==='tool' && m.source?.callId===task.callId)
      if (task.tool && !already) {
        yield {type:'block-start',index:0,blockType:'tool-call'}
        yield {type:'block-end',index:0,block:{type:'tool-call',id:task.callId,name:task.tool,arguments:JSON.stringify(task.args)}}
        yield {type:'finish',reason:{kind:'tool-calls'}}
      } else {
        yield {type:'block-start',index:0,blockType:'text'}
        yield {type:'block-end',index:0,block:{type:'text',text:task.answer}}
        yield {type:'finish',reason:{kind:'stop'}}
      }
    }
  }
  ctx.llm.registerAdapter(['actio-fixture'],new Fixture())
}
