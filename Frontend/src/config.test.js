import { resolveApiBaseUrl } from './config';

describe('API base URL configuration', () => {
  test('keeps the localhost default available in development', () => {
    expect(resolveApiBaseUrl('development', '')).toBe('http://localhost:8000');
  });

  test('rejects a missing production API URL instead of falling back to localhost', () => {
    expect(() => resolveApiBaseUrl('production', '')).toThrow(/API_BASE_URL must be set/i);
  });

  test.each(['http://localhost:8000', 'https://localhost:8000', 'https://127.0.0.1:8000'])(
    'rejects loopback production API URL %s',
    (url) => expect(() => resolveApiBaseUrl('production', url)).toThrow(/must use HTTPS.*localhost/i)
  );

  test('rejects malformed and non-HTTP API URLs', () => {
    expect(() => resolveApiBaseUrl('development', 'not a URL')).toThrow(/absolute HTTP\(S\) URL/i);
    expect(() => resolveApiBaseUrl('development', 'file:///tmp/api')).toThrow(/absolute HTTP\(S\) URL/i);
    expect(() => resolveApiBaseUrl('production', 'https://user:pass@api.example.com')).toThrow(/embedded credentials/i);
    expect(() => resolveApiBaseUrl('production', 'https://api.example.com?token=unsafe')).toThrow(/query/i);
  });

  test('accepts a configured HTTPS production API URL and removes trailing slashes', () => {
    expect(resolveApiBaseUrl('production', 'https://api.example.com/')).toBe('https://api.example.com');
  });
});
