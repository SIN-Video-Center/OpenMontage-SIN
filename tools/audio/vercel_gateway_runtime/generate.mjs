import {writeFile} from 'node:fs/promises';
import process from 'node:process';
import {experimental_generateSpeech as generateSpeech} from 'ai';
import {createGateway} from '@ai-sdk/gateway';

const readStdin = async () => {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
};

const safeJson = (value) => JSON.parse(JSON.stringify(value, (_key, item) => {
  if (item instanceof Date) return item.toISOString();
  if (item instanceof Uint8Array) return undefined;
  if (typeof item === 'bigint') return Number(item);
  return item;
}));

const failurePayload = (error) => {
  const statusCode = Number(
    error?.statusCode ?? error?.status ?? error?.response?.status ?? error?.cause?.statusCode ?? 0,
  ) || null;
  const message = String(error?.message ?? error ?? 'AI Gateway speech generation failed').slice(0, 500);
  const retryable = statusCode === null || [401, 402, 403, 408, 409, 429, 500, 502, 503, 504].includes(statusCode);
  return {success: false, error: message, statusCode, retryable};
};

try {
  const input = await readStdin();
  const apiKey = process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_AI_GATEWAY_API_KEY;
  if (!apiKey) throw new Error('AI_GATEWAY_API_KEY is not set for the speech runtime');
  if (!input.outputPath) throw new Error('outputPath is required');

  const gateway = createGateway({
    apiKey,
    ...(input.baseURL ? {baseURL: input.baseURL} : {}),
  });

  const result = await generateSpeech({
    model: gateway.speechModel(input.model),
    text: input.text,
    voice: input.voice,
    outputFormat: input.outputFormat,
    ...(input.speed !== undefined ? {speed: input.speed} : {}),
    ...(input.language ? {language: input.language} : {}),
    ...(input.instructions ? {instructions: input.instructions} : {}),
    maxRetries: 0,
  });

  await writeFile(input.outputPath, result.audio.uint8Array);
  const firstResponse = Array.isArray(result.responses) ? result.responses[0] : undefined;
  process.stdout.write(JSON.stringify({
    success: true,
    mediaType: result.audio.mediaType,
    format: result.audio.format,
    byteLength: result.audio.uint8Array.byteLength,
    warnings: safeJson(result.warnings ?? []),
    providerMetadata: safeJson(result.providerMetadata ?? {}),
    response: firstResponse ? safeJson({
      modelId: firstResponse.modelId,
      timestamp: firstResponse.timestamp,
      headers: firstResponse.headers,
    }) : null,
  }));
} catch (error) {
  process.stdout.write(JSON.stringify(failurePayload(error)));
  process.exitCode = 2;
}
