/** One bounded in-flight transfer per ordered socket; incomplete state never escapes. */
export class EnvelopeChunks {
  private transfer: {id:string;total:number;parts:string[];length:number;started:number} | null = null;
  clear() { this.transfer = null; }
  push(payload: {id:string;index:number;total:number;data:string}, now = Date.now()): string | null {
    const {id,index,total,data} = payload;
    if (typeof id !== 'string' || !Number.isInteger(index) || !Number.isInteger(total)
      || total < 1 || total > 2048 || index < 0 || index >= total || typeof data !== 'string' || data.length > 65536)
      throw new Error('Invalid state chunk');
    if (!this.transfer || this.transfer.id !== id) {
      if (index !== 0) throw new Error('Missing initial state chunk');
      this.transfer = {id,total,parts:[],length:0,started:now};
    }
    const transfer = this.transfer;
    if (now - transfer.started > 30000 || total !== transfer.total) { this.clear(); throw new Error('Expired state transfer'); }
    if (index < transfer.parts.length && transfer.parts[index] === data) return null;
    if (index !== transfer.parts.length) { this.clear(); throw new Error('Missing state chunk'); }
    transfer.parts.push(data);
    transfer.length += data.length;
    // Operational memory safeguard, unrelated to any deployment quantity rule.
    if (transfer.length > 128 * 1024 * 1024) { this.clear(); throw new Error('State transfer memory budget exceeded'); }
    if (transfer.parts.length !== total) return null;
    this.clear();
    return transfer.parts.join('');
  }
}
