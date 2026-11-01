import axios, { AxiosError } from 'axios';
import apiClient, {
  clearCsrfToken,
  refreshCsrfToken,
  setCsrfToken,
} from '../apiClient';
import { logout } from '../authService';

describe('CSRF request handling', () => {
  let sentConfigs;
  let originalLocksDescriptor;
  let originalStorageDescriptor;
  let previousTimeout;

  beforeEach(() => {
    sentConfigs = [];
    jest.restoreAllMocks();
    originalLocksDescriptor = Object.getOwnPropertyDescriptor(navigator, 'locks');
    originalStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    previousTimeout = process.env.CSRF_BOOTSTRAP_TIMEOUT_MS;
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: { request: jest.fn((_name, _options, operation) => operation()) },
    });
    clearCsrfToken();
    jest.spyOn(axios, 'get').mockResolvedValue({ data: { csrf_token: 'fresh-token' } });
    apiClient.defaults.adapter = async (config) => {
      sentConfigs.push(config);
      return {
        data: { ok: true },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    };
  });

  afterEach(() => {
    clearCsrfToken();
    jest.useRealTimers();
    if (previousTimeout === undefined) delete process.env.CSRF_BOOTSTRAP_TIMEOUT_MS;
    else process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = previousTimeout;
    delete navigator.locks;
    if (originalLocksDescriptor) Object.defineProperty(navigator, 'locks', originalLocksDescriptor);
    if (originalStorageDescriptor) Object.defineProperty(window, 'localStorage', originalStorageDescriptor);
  });

  test('fetches a token and adds the custom header to unsafe requests', async () => {
    await apiClient.post('/chat/query', { query: 'question' });
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get).toHaveBeenCalledWith(
      '/users/csrf',
      expect.objectContaining({ withCredentials: true, timeout: 10000 })
    );
    expect(sentConfigs[0].headers.get('X-CSRF-Token')).toBe('fresh-token');
  });

  test('shares one in-flight bootstrap across simultaneous requests', async () => {
    let finishBootstrap;
    axios.get.mockReturnValue(
      new Promise((resolve) => {
        finishBootstrap = resolve;
      })
    );

    const first = apiClient.post('/chat/query', { query: 'one' });
    const second = apiClient.post('/documents/upload', {});
    await Promise.resolve();
    expect(axios.get).toHaveBeenCalledTimes(1);

    finishBootstrap({ data: { csrf_token: 'shared-token' } });
    await Promise.all([first, second]);
    expect(sentConfigs).toHaveLength(2);
    expect(sentConfigs.every((config) => config.headers.get('X-CSRF-Token') === 'shared-token')).toBe(true);
  });

  test('uses the cross-tab Web Lock when the browser supports it', async () => {
    const request = jest.fn((_name, _options, operation) => operation());
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: { request },
    });
    await apiClient.post('/chat/query', { query: 'question' });
    expect(request).toHaveBeenCalledWith(
      'learning-assistant-csrf-bootstrap',
      { mode: 'exclusive', signal: expect.anything() },
      expect.any(Function)
    );
  });

  test('cancels a queued Web Lock request on timeout without releasing another tab lock', async () => {
    process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = '25';
    jest.useFakeTimers();
    let requestOptions;
    const otherTabLock = { held: true };
    navigator.locks.request = jest.fn((_name, options) => {
      requestOptions = options;
      // The other tab owns the lock, so the callback stays queued.
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new Error('queued request aborted')));
      });
    });

    const request = apiClient.post('/chat/query', { query: 'queued' });
    const result = expect(request).rejects.toThrow('CSRF bootstrap timed out');
    await Promise.resolve();
    await jest.advanceTimersByTimeAsync(25);
    await result;

    expect(requestOptions.signal.aborted).toBe(true);
    expect(navigator.locks.request).toHaveBeenCalledTimes(1);
    expect(otherTabLock.held).toBe(true);
    expect(axios.get).not.toHaveBeenCalled();
    expect(sentConfigs).toHaveLength(0);
  });

  test('rejects invalid or nonpositive bootstrap timeout configuration', async () => {
    for (const value of ['0', '-1', 'not-a-number', '1.5']) {
      process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = value;
      await expect(apiClient.post('/chat/query', { query: 'question' })).rejects.toThrow(
        'CSRF_BOOTSTRAP_TIMEOUT_MS must be a positive integer'
      );
    }
    expect(axios.get).not.toHaveBeenCalled();
    expect(sentConfigs).toHaveLength(0);
  });

  test('rejects bootstrap timeouts above the 30-second maximum', async () => {
    process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = '30001';
    await expect(apiClient.post('/chat/query', { query: 'too long' })).rejects.toThrow(
      'CSRF_BOOTSTRAP_TIMEOUT_MS must be a positive integer'
    );
    expect(axios.get).not.toHaveBeenCalled();
    expect(sentConfigs).toHaveLength(0);
  });

  test('times out shared bootstrap waiters and sends neither mutation', async () => {
    process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = '25';
    jest.useFakeTimers();
    axios.get.mockReturnValue(new Promise(() => {}));
    const first = apiClient.post('/chat/query', { query: 'one' });
    const second = apiClient.post('/documents/upload', {});
    const firstResult = expect(first).rejects.toThrow('CSRF bootstrap timed out');
    const secondResult = expect(second).rejects.toThrow('CSRF bootstrap timed out');
    await Promise.resolve();
    await jest.advanceTimersByTimeAsync(25);
    await Promise.all([firstResult, secondResult]);
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(sentConfigs).toHaveLength(0);
  });

  test('cleans up a timed-out bootstrap and ignores its late response', async () => {
    process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = '25';
    jest.useFakeTimers();
    let finishFirstBootstrap;
    axios.get
      .mockReturnValueOnce(new Promise((resolve) => { finishFirstBootstrap = resolve; }))
      .mockResolvedValueOnce({ data: { csrf_token: 'recovered-token' } });

    const timedOutRequest = apiClient.post('/chat/query', { query: 'first' });
    const timedOutResult = expect(timedOutRequest).rejects.toThrow('CSRF bootstrap timed out');
    await Promise.resolve();
    await jest.advanceTimersByTimeAsync(25);
    await timedOutResult;

    const recoveredRequest = apiClient.post('/chat/query', { query: 'second' });
    await Promise.resolve();
    finishFirstBootstrap({ data: { csrf_token: 'late-stale-token' } });
    await jest.advanceTimersByTimeAsync(0);
    await recoveredRequest;

    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(sentConfigs).toHaveLength(1);
    expect(sentConfigs[0].headers.get('X-CSRF-Token')).toBe('recovered-token');
  });

  test('lease fallback refuses to bootstrap while another tab owns the lease', async () => {
    delete navigator.locks;
    process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = '30';
    window.localStorage.setItem('learning-assistant:csrf-bootstrap-lease', JSON.stringify({
      owner: 'another-tab', expiresAt: Date.now() + 5000,
    }));

    await expect(apiClient.post('/chat/query', { query: 'blocked' })).rejects.toThrow();
    expect(axios.get).not.toHaveBeenCalled();
    window.localStorage.removeItem('learning-assistant:csrf-bootstrap-lease');
  });

  test('lease fallback verifies election ownership and removes its temporary lease', async () => {
    delete navigator.locks;
    await apiClient.post('/chat/query', { query: 'lease fallback' });
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(sentConfigs).toHaveLength(1);
    expect(window.localStorage.getItem('learning-assistant:csrf-bootstrap-lease')).toBeNull();
    const remainingCandidates = Array.from({ length: window.localStorage.length }, (_item, index) =>
      window.localStorage.key(index)
    ).filter((key) => key && key.startsWith('learning-assistant:csrf-bootstrap-candidate:'));
    expect(remainingCandidates).toHaveLength(0);
  });

  test('lease fallback recovers an expired lease and completes bootstrap', async () => {
    delete navigator.locks;
    window.localStorage.setItem('learning-assistant:csrf-bootstrap-lease', JSON.stringify({
      owner: 'crashed-tab', expiresAt: Date.now() - 1,
    }));

    await apiClient.post('/chat/query', { query: 'recover expired lease' });

    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(sentConfigs).toHaveLength(1);
    expect(sentConfigs[0].headers.get('X-CSRF-Token')).toBe('fresh-token');
    expect(window.localStorage.getItem('learning-assistant:csrf-bootstrap-lease')).toBeNull();
  });

  test('lease fallback yields to a competing candidate instead of fetching', async () => {
    delete navigator.locks;
    process.env.CSRF_BOOTSTRAP_TIMEOUT_MS = '250';
    window.localStorage.setItem(
      'learning-assistant:csrf-bootstrap-candidate:competing-owner',
      JSON.stringify({ owner: '', expiresAt: Date.now() + 5000 })
    );

    await expect(apiClient.post('/chat/query', { query: 'contended' })).rejects.toThrow();
    expect(axios.get).not.toHaveBeenCalled();
    window.localStorage.removeItem('learning-assistant:csrf-bootstrap-candidate:competing-owner');
  });

  test('fails closed when neither Web Locks nor usable local storage is available', async () => {
    delete navigator.locks;
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() { throw new Error('storage disabled'); },
    });

    await expect(apiClient.post('/chat/query', { query: 'blocked' })).rejects.toThrow(
      'Safe cross-tab CSRF coordination is unavailable'
    );
    expect(axios.get).not.toHaveBeenCalled();
  });

  test('cross-tab login and logout notifications invalidate stale in-memory tokens', async () => {
    setCsrfToken('stale-token');
    const sendStorageInvalidation = (reason, id) => window.dispatchEvent(new StorageEvent('storage', {
      key: 'learning-assistant:csrf-session-event',
      newValue: JSON.stringify({ type: 'csrf-session-invalidated', reason, id }),
    }));

    sendStorageInvalidation('logout', 'logout-event');
    await apiClient.post('/chat/query', { query: 'after logout' });
    expect(sentConfigs[0].headers.get('X-CSRF-Token')).toBe('fresh-token');

    setCsrfToken('stale-again');
    axios.get.mockResolvedValue({ data: { csrf_token: 'post-login-token' } });
    sendStorageInvalidation('login', 'login-event');
    sendStorageInvalidation('login', 'login-event');
    await new Promise((resolve) => setTimeout(resolve, 0));
    await apiClient.post('/chat/query', { query: 'after login' });
    expect(sentConfigs[1].headers.get('X-CSRF-Token')).toBe('post-login-token');
    expect(axios.get).toHaveBeenCalledTimes(2);
  });

  test('browser storage contains no JWT or CSRF token values', () => {
    const jwtValue = 'jwt-secret-value-for-test';
    const csrfValue = 'csrf-secret-value-for-test';
    setCsrfToken(csrfValue);
    const stored = Array.from({ length: window.localStorage.length }, (_item, index) => {
      const key = window.localStorage.key(index);
      return `${key}=${window.localStorage.getItem(key)}`;
    }).join('\n');
    expect(stored).not.toContain(jwtValue);
    expect(stored).not.toContain(csrfValue);
  });

  test('does not bootstrap or add a CSRF header for safe GET requests', async () => {
    await apiClient.get('/users/me');
    expect(axios.get).not.toHaveBeenCalled();
    expect(sentConfigs[0].headers.get('X-CSRF-Token')).toBeUndefined();
  });

  test('refreshes after a CSRF rejection but does not retry the failed mutation', async () => {
    setCsrfToken('expired-token');
    apiClient.defaults.adapter = async (config) => {
      sentConfigs.push(config);
      throw new AxiosError(
        'Request failed with status code 403',
        'ERR_BAD_REQUEST',
        config,
        null,
        {
          data: { detail: 'CSRF token is missing or invalid' },
          status: 403,
          statusText: 'Forbidden',
          headers: {},
          config,
        }
      );
    };

    await expect(apiClient.post('/chat/query', { query: 'question' })).rejects.toThrow(
      'CSRF token is missing or invalid'
    );
    expect(sentConfigs).toHaveLength(1);
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test('explicit refresh uses the shared bootstrap operation', async () => {
    const [first, second] = await Promise.all([refreshCsrfToken(), refreshCsrfToken()]);
    expect(first).toBe('fresh-token');
    expect(second).toBe('fresh-token');
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test('clears in-memory CSRF state when logout fails and does not repeat logout', async () => {
    setCsrfToken('authenticated-token');
    let logoutCalls = 0;
    apiClient.defaults.adapter = async (config) => {
      sentConfigs.push(config);
      if (config.url === '/users/logout') {
        logoutCalls += 1;
        throw new AxiosError('server error', 'ERR_BAD_RESPONSE', config, null, {
          data: { detail: 'temporary failure' }, status: 500,
          statusText: 'Internal Server Error', headers: {}, config,
        });
      }
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
    };

    await expect(logout()).rejects.toThrow('temporary failure');
    await apiClient.post('/chat/query', { query: 'retry manually' });
    expect(logoutCalls).toBe(1);
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(sentConfigs).toHaveLength(2);
  });
});
