// Chunked transfer for payloads larger than one MCP request (~100 KB).
// Python sends `chunkPut(id, index, total, part)` `total` times, then the real call does
// `JSON.parse(pb.chunkTake(id))`.
import { runtime } from "./state";

export const chunkPut = (id: string, index: number, total: number, data: string): number => {
  (runtime.chunks[id] = runtime.chunks[id] || { total, parts: [] }).parts[index] = data;
  return index;
};

export const chunkTake = (id: string): string => {
  const transfer = runtime.chunks[id];
  if (!transfer) throw new Error("chunk " + id + " missing");
  if (transfer.parts.filter(part => part !== undefined).length !== transfer.total) throw new Error("chunk " + id + " incomplete");
  delete runtime.chunks[id];
  return transfer.parts.join("");
};
