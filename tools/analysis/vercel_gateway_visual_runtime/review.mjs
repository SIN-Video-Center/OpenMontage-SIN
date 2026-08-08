import {readFile} from 'node:fs/promises';
import process from 'node:process';
import {createGateway} from '@ai-sdk/gateway';
import {generateText} from 'ai';

const RETRYABLE_STATUS = new Set([401, 402, 403, 408, 409, 429, 500, 502, 503, 504]);

const readStdin = async () => {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
};

const mediaTypeFor = (path) => {
  const lower = path.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  return 'image/jpeg';
};

const extractJson = (text) => {
  const trimmed = String(text || '').trim();
  if (!trimmed) throw new Error('Vision reviewer returned empty text');
  try { return JSON.parse(trimmed); } catch {}
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced) return JSON.parse(fenced[1]);
  const first = trimmed.indexOf('{');
  const last = trimmed.lastIndexOf('}');
  if (first >= 0 && last > first) return JSON.parse(trimmed.slice(first, last + 1));
  throw new Error(`Vision reviewer returned non-JSON text: ${trimmed.slice(0, 240)}`);
};

const findGenerationId = (value) => {
  if (!value || typeof value !== 'object') return undefined;
  for (const [key, child] of Object.entries(value)) {
    if ((key === 'generationId' || key === 'generation_id' || key === 'id') && typeof child === 'string' && child.startsWith('gen_')) return child;
    const nested = findGenerationId(child);
    if (nested) return nested;
  }
  return undefined;
};

const main = async () => {
  const payload = JSON.parse(await readStdin());
  const apiKey = process.env.AI_GATEWAY_API_KEY;
  if (!apiKey) throw new Error('AI_GATEWAY_API_KEY is missing');
  const gateway = createGateway({apiKey, ...(payload.baseURL ? {baseURL: payload.baseURL} : {})});

  const imageParts = [];
  for (const frame of payload.frames || []) {
    imageParts.push({
      type: 'image',
      image: await readFile(frame.path),
      mediaType: frame.mediaType || mediaTypeFor(frame.path),
    });
    imageParts.push({type: 'text', text: `FRAME ${frame.index}: ${frame.label || ''} timestamp=${frame.timestampSeconds ?? 'unknown'}s scene=${frame.sceneId || 'unknown'}`});
  }

  const result = await generateText({
    model: gateway.languageModel(payload.model),
    system: payload.systemPrompt,
    messages: [{
      role: 'user',
      content: [{type: 'text', text: payload.userPrompt}, ...imageParts],
    }],
    temperature: payload.temperature ?? 0.1,
    maxOutputTokens: payload.maxOutputTokens ?? 5000,
  });

  const review = extractJson(result.text);
  const generationId = findGenerationId(result.providerMetadata);
  let generationInfo;
  if (generationId) {
    try { generationInfo = await gateway.getGenerationInfo({id: generationId}); } catch {}
  }

  process.stdout.write(JSON.stringify({
    success: true,
    review,
    usage: result.usage,
    warnings: result.warnings || [],
    providerMetadata: result.providerMetadata || {},
    response: result.response || {},
    generationId,
    generationInfo,
  }));
};

main().catch((error) => {
  const statusCode = error?.statusCode ?? error?.cause?.statusCode;
  const retryable = error?.isRetryable ?? RETRYABLE_STATUS.has(statusCode);
  process.stdout.write(JSON.stringify({
    success: false,
    error: String(error?.message || error),
    statusCode: statusCode ?? null,
    retryable: Boolean(retryable),
  }));
  process.exitCode = 1;
});
