const DEVELOPMENT_API_BASE_URL = 'http://localhost:8000';

export function resolveApiBaseUrl(environment, configuredUrl) {
  const isProduction = environment === 'production';
  const value = typeof configuredUrl === 'string' ? configuredUrl.trim() : '';

  if (!value) {
    if (isProduction) {
      throw new Error('API_BASE_URL must be set to the HTTPS backend URL for production builds');
    }
    return DEVELOPMENT_API_BASE_URL;
  }

  let parsedUrl;
  try {
    if (!/^https?:\/\//i.test(value)) throw new Error('scheme required');
    parsedUrl = new URL(value);
  } catch (_error) {
    throw new Error('API_BASE_URL must be an absolute HTTP(S) URL');
  }

  if (
    !['http:', 'https:'].includes(parsedUrl.protocol) ||
    !parsedUrl.hostname ||
    parsedUrl.username ||
    parsedUrl.password ||
    parsedUrl.search ||
    parsedUrl.hash
  ) {
    throw new Error('API_BASE_URL must be an absolute HTTP(S) URL without embedded credentials, query, or fragment');
  }

  if (isProduction) {
    const hostname = parsedUrl.hostname.toLowerCase();
    const isLoopback =
      hostname === 'localhost' ||
      hostname.endsWith('.localhost') ||
      hostname === '127.0.0.1' ||
      hostname === '::1' ||
      hostname === '[::1]';
    if (parsedUrl.protocol !== 'https:' || isLoopback) {
      throw new Error('Production API_BASE_URL must use HTTPS and must not point to localhost');
    }
  }

  return value.replace(/\/+$/, '');
}

export const API_BASE_URL = resolveApiBaseUrl(process.env.NODE_ENV, process.env.API_BASE_URL);
