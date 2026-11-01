/**
 * Centralized Axios API Client.
 *
 * The JWT remains in its HttpOnly cookie. The CSRF token is held only in this
 * module's memory; browser storage contains coordination metadata only.
 */

import axios from 'axios';

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';
const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete']);
const CSRF_FAILURE_DETAIL = 'CSRF token is missing or invalid';
const DEFAULT_CSRF_BOOTSTRAP_TIMEOUT_MS = 10000;
const MAX_CSRF_BOOTSTRAP_TIMEOUT_MS = 30000;
const CSRF_LOCK_NAME = 'learning-assistant-csrf-bootstrap';
const CSRF_LEASE_KEY = 'learning-assistant:csrf-bootstrap-lease';
const CSRF_CANDIDATE_PREFIX = 'learning-assistant:csrf-bootstrap-candidate:';
const CSRF_EVENT_KEY = 'learning-assistant:csrf-session-event';
const LEASE_SETTLE_MS = 60;
const LEASE_CHECK_MS = 40;

let csrfToken = null;
let csrfBootstrapPromise = null;
let csrfBootstrapCancellation = null;
let csrfGeneration = 0;
let csrfChannel = null;
const handledInvalidationIds = new Set();

try {
  if (typeof BroadcastChannel !== 'undefined') {
    csrfChannel = new BroadcastChannel('learning-assistant-csrf');
  }
} catch (_channelError) {
  // Storage events remain the cross-tab notification fallback.
}

function getBootstrapTimeoutMs() {
  const configured = process.env.CSRF_BOOTSTRAP_TIMEOUT_MS;
  if (configured === undefined) return DEFAULT_CSRF_BOOTSTRAP_TIMEOUT_MS;
  if (!/^\d+$/.test(configured)) {
    throw createCsrfBootstrapError('CSRF_BOOTSTRAP_TIMEOUT_MS must be a positive integer');
  }
  const timeout = Number(configured);
  if (!Number.isSafeInteger(timeout) || timeout <= 0 || timeout > MAX_CSRF_BOOTSTRAP_TIMEOUT_MS) {
    throw createCsrfBootstrapError('CSRF_BOOTSTRAP_TIMEOUT_MS must be a positive integer');
  }
  return timeout;
}

function createCsrfBootstrapError(message) {
  const error = new Error(message);
  error.code = 'ERR_CSRF_BOOTSTRAP';
  return error;
}

function createCancellation() {
  if (typeof AbortController !== 'undefined') {
    const controller = new AbortController();
    return {
      signal: controller.signal,
      axiosSignal: controller.signal,
      abort: () => controller.abort(),
    };
  }

  let aborted = false;
  const listeners = new Set();
  const signal = {
    get aborted() { return aborted; },
    addEventListener(_type, listener) { listeners.add(listener); },
    removeEventListener(_type, listener) { listeners.delete(listener); },
  };
  return {
    signal,
    axiosSignal: null,
    abort: () => {
      if (aborted) return;
      aborted = true;
      listeners.forEach((listener) => listener());
      listeners.clear();
    },
  };
}

function coordinationOwnerId() {
  try {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
      return globalThis.crypto.randomUUID();
    }
  } catch (_cryptoError) {
    // This ID is coordination metadata, not an authentication secret.
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function getCoordinationStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch (_storageError) {
    return null;
  }
}

function readLease(storage) {
  const raw = storage.getItem(CSRF_LEASE_KEY);
  if (raw === null) return null;
  try {
    const lease = JSON.parse(raw);
    if (typeof lease.owner !== 'string' || !Number.isFinite(lease.expiresAt)) {
      throw new Error('Invalid lease');
    }
    return lease;
  } catch (_leaseError) {
    throw new Error('CSRF bootstrap coordination state is invalid');
  }
}

function listLeaseCandidates(storage, now) {
  const candidates = [];
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (!key || !key.startsWith(CSRF_CANDIDATE_PREFIX)) continue;
    let candidate;
    try {
      candidate = JSON.parse(storage.getItem(key));
    } catch (_candidateError) {
      throw new Error('CSRF bootstrap coordination state is invalid');
    }
    if (!candidate || typeof candidate.owner !== 'string' || !Number.isFinite(candidate.expiresAt)) {
      throw new Error('CSRF bootstrap coordination state is invalid');
    }
    if (candidate.expiresAt <= now) storage.removeItem(key);
    else candidates.push(candidate);
  }
  return candidates.sort((left, right) => left.owner.localeCompare(right.owner));
}

function waitForCoordination(ms, signal) {
  if (signal.aborted) return Promise.reject(new Error('CSRF bootstrap was superseded'));
  return new Promise((resolve, reject) => {
    let timer;
    const onAbort = () => {
      clearTimeout(timer);
      reject(new Error('CSRF bootstrap was superseded'));
    };
    timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

function awaitOrAbort(promise, signal) {
  let onAbort;
  const aborted = new Promise((_resolve, reject) => {
    if (signal.aborted) {
      reject(new Error('CSRF bootstrap was superseded'));
      return;
    }
    onAbort = () => reject(new Error('CSRF bootstrap was superseded'));
    signal.addEventListener('abort', onAbort, { once: true });
  });
  return Promise.race([promise, aborted]).finally(() => {
    if (onAbort) signal.removeEventListener('abort', onAbort);
  });
}

async function withStorageLease(operation, signal, timeoutMs) {
  const storage = getCoordinationStorage();
  if (!storage) {
    throw new Error('Safe cross-tab CSRF coordination is unavailable in this browser');
  }

  const owner = coordinationOwnerId();
  const candidateKey = `${CSRF_CANDIDATE_PREFIX}${owner}`;
  if (storage.getItem(candidateKey) !== null) {
    throw new Error('CSRF bootstrap coordination owner collision');
  }
  const deadline = Date.now() + timeoutMs;
  const leaseDuration = timeoutMs + 5000;
  try {
    while (!signal.aborted && Date.now() < deadline) {
      const now = Date.now();
      const currentLease = readLease(storage);
      if (currentLease && currentLease.expiresAt > now) {
        await waitForCoordination(Math.min(LEASE_CHECK_MS, currentLease.expiresAt - now), signal);
        continue;
      }
      if (currentLease) storage.removeItem(CSRF_LEASE_KEY);

      // Distinct candidate records and repeated ownership checks reduce races.
      // A shared localStorage read-then-write is not treated as an atomic lock.
      storage.setItem(candidateKey, JSON.stringify({ owner, expiresAt: now + leaseDuration }));
      const appearedLease = readLease(storage);
      if (appearedLease && appearedLease.expiresAt > Date.now()) {
        storage.removeItem(candidateKey);
        await waitForCoordination(LEASE_CHECK_MS, signal);
        continue;
      }

      await waitForCoordination(LEASE_SETTLE_MS + Math.floor(Math.random() * LEASE_CHECK_MS), signal);
      const leaseBeforeClaim = readLease(storage);
      const candidates = listLeaseCandidates(storage, Date.now());
      if ((leaseBeforeClaim && leaseBeforeClaim.expiresAt > Date.now())
          || !candidates.length || candidates[0].owner !== owner) {
        storage.removeItem(candidateKey);
        await waitForCoordination(LEASE_CHECK_MS, signal);
        continue;
      }

      const claimedLease = { owner, expiresAt: Date.now() + leaseDuration };
      storage.setItem(CSRF_LEASE_KEY, JSON.stringify(claimedLease));
      await waitForCoordination(LEASE_CHECK_MS, signal);
      const verifiedLease = readLease(storage);
      const verifiedCandidates = listLeaseCandidates(storage, Date.now());
      if (!verifiedLease || verifiedLease.owner !== owner
          || verifiedLease.expiresAt <= Date.now()
          || !verifiedCandidates.length || verifiedCandidates[0].owner !== owner) {
        if (verifiedLease && verifiedLease.owner === owner) storage.removeItem(CSRF_LEASE_KEY);
        storage.removeItem(candidateKey);
        continue;
      }

      return await operation(() => {
        const latestLease = readLease(storage);
        if (!latestLease || latestLease.owner !== owner || latestLease.expiresAt <= Date.now()) {
          throw new Error('CSRF bootstrap coordination lease was lost');
        }
      });
    }
    throw new Error('Safe cross-tab CSRF coordination could not be established');
  } finally {
    try {
      storage.removeItem(candidateKey);
      const lease = readLease(storage);
      if (lease && lease.owner === owner) storage.removeItem(CSRF_LEASE_KEY);
    } catch (_cleanupError) {
      // Any abandoned lease expires and is reclaimed by a later contender.
    }
  }
}

function withExclusiveCoordination(operation, signal, timeoutMs) {
  const locks = typeof navigator !== 'undefined' && navigator.locks;
  if (locks && typeof locks.request === 'function') {
    return locks.request(CSRF_LOCK_NAME, { mode: 'exclusive', signal }, async () => {
      if (signal.aborted) throw new Error('CSRF bootstrap was superseded');
      return operation(() => {
        if (signal.aborted) throw new Error('CSRF bootstrap was superseded');
      });
    });
  }
  return withStorageLease(operation, signal, timeoutMs);
}

function notifyTabs(reason) {
  const message = { type: 'csrf-session-invalidated', reason, id: coordinationOwnerId() };
  if (csrfChannel) {
    try { csrfChannel.postMessage(message); } catch (_channelError) { /* use storage event fallback */ }
  }
  const storage = getCoordinationStorage();
  if (storage) {
    try {
      const serialized = JSON.stringify(message);
      storage.setItem(CSRF_EVENT_KEY, serialized);
      setTimeout(() => {
        try {
          if (storage.getItem(CSRF_EVENT_KEY) === serialized) storage.removeItem(CSRF_EVENT_KEY);
        } catch (_cleanupError) { /* notification is best effort */ }
      }, 100);
    } catch (_storageError) {
      // Other tabs may still receive the BroadcastChannel notification.
    }
  }
}

function requestCsrfToken() {
  if (csrfBootstrapPromise) return csrfBootstrapPromise;

  const timeoutMs = getBootstrapTimeoutMs();
  const cancellation = createCancellation();
  const { signal } = cancellation;
  const generation = csrfGeneration;
  let timeoutId;
  let bootstrapPromise;

  const operation = async (assertExclusive) => {
    assertExclusive();
    if (signal.aborted) throw new Error('CSRF bootstrap was superseded');
    if (csrfGeneration !== generation) {
      if (csrfToken) return csrfToken;
      throw new Error('CSRF bootstrap was superseded');
    }
    const response = await awaitOrAbort(axios.get('/users/csrf', {
      baseURL: API_BASE_URL,
      withCredentials: true,
      headers: { Accept: 'application/json' },
      timeout: timeoutMs,
      ...(cancellation.axiosSignal ? { signal: cancellation.axiosSignal } : {}),
    }), signal);
    assertExclusive();
    if (signal.aborted || csrfGeneration !== generation) {
      throw new Error('CSRF bootstrap response was superseded');
    }
    const token = response.data && response.data.csrf_token;
    if (typeof token !== 'string' || !token) throw new Error('CSRF bootstrap returned no token');
    csrfToken = token;
    return token;
  };

  const work = withExclusiveCoordination(operation, signal, timeoutMs).catch((error) => {
    const safeMessage = error && typeof error.message === 'string'
      ? error.message
      : 'CSRF bootstrap failed; retry the request';
    throw createCsrfBootstrapError(safeMessage);
  });
  const timedOut = new Promise((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      cancellation.abort();
      reject(createCsrfBootstrapError('CSRF bootstrap timed out; retry the request'));
    }, timeoutMs);
  });
  bootstrapPromise = Promise.race([work, timedOut]).finally(() => {
    clearTimeout(timeoutId);
    if (csrfBootstrapCancellation === cancellation) csrfBootstrapCancellation = null;
    if (csrfBootstrapPromise === bootstrapPromise) csrfBootstrapPromise = null;
  });
  csrfBootstrapCancellation = cancellation;
  csrfBootstrapPromise = bootstrapPromise;
  return bootstrapPromise;
}

function cancelBootstrapForStateChange() {
  csrfGeneration += 1;
  const previousPromise = csrfBootstrapPromise;
  csrfBootstrapPromise = null;
  if (csrfBootstrapCancellation) csrfBootstrapCancellation.abort();
  csrfBootstrapCancellation = null;
  return previousPromise;
}

function handleRemoteInvalidation(message) {
  if (!message || !message.id || handledInvalidationIds.has(message.id)) return;
  handledInvalidationIds.add(message.id);
  if (handledInvalidationIds.size > 100) {
    handledInvalidationIds.delete(handledInvalidationIds.values().next().value);
  }
  const { reason } = message;
  cancelBootstrapForStateChange();
  csrfToken = null;
  if (reason !== 'logout') {
    requestCsrfToken().catch(() => {
      // A later unsafe request can try again; no mutation is replayed.
    });
  }
}

if (csrfChannel) {
  csrfChannel.addEventListener('message', ({ data }) => {
    if (data && data.type === 'csrf-session-invalidated') handleRemoteInvalidation(data);
  });
}

if (typeof window !== 'undefined' && window.addEventListener) {
  window.addEventListener('storage', (event) => {
    if (event.key !== CSRF_EVENT_KEY || !event.newValue) return;
    try {
      const message = JSON.parse(event.newValue);
      if (message && message.type === 'csrf-session-invalidated') handleRemoteInvalidation(message);
    } catch (_eventError) {
      // Ignore malformed coordination metadata; it contains no credentials.
    }
  });
}

export function setCsrfToken(token) {
  cancelBootstrapForStateChange();
  csrfToken = token || null;
  notifyTabs('login');
}

export function clearCsrfToken(reason = 'logout') {
  cancelBootstrapForStateChange();
  csrfToken = null;
  notifyTabs(reason);
}

export function refreshCsrfToken() {
  if (csrfBootstrapPromise) return csrfBootstrapPromise;
  clearCsrfToken('refresh');
  return requestCsrfToken();
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Sends the HttpOnly access_token cookie.
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
  timeout: 60000,
});

apiClient.interceptors.request.use(async (config) => {
  const method = (config.method || 'get').toLowerCase();
  if (!UNSAFE_METHODS.has(method)) return config;

  const token = csrfToken || (await requestCsrfToken());
  if (config.headers && typeof config.headers.set === 'function') {
    config.headers.set('X-CSRF-Token', token);
  } else {
    config.headers = config.headers || {};
    config.headers['X-CSRF-Token'] = token;
  }
  return config;
});

function normalizeError(error) {
  if (!error.response) {
    if (error.code === 'ERR_CSRF_BOOTSTRAP') return error;
    return new Error('Unable to connect to the server. Please ensure the backend is running.');
  }
  const { data, status } = error.response;
  if (data && typeof data.detail === 'string') return new Error(data.detail);
  if (data && Array.isArray(data.detail)) {
    const messages = data.detail.map((item) => {
      const field = item.loc && item.loc.length > 1 ? item.loc.slice(1).join('.') : 'Field';
      return `${field}: ${item.msg}`;
    });
    return new Error(messages.join(' · '));
  }
  const statusMessages = {
    400: 'Invalid request. Please check your input.',
    401: 'Your session has expired. Please log in again.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested resource was not found.',
    409: 'A conflict occurred. This item may already exist.',
    422: 'The provided data is invalid. Please check your input.',
    500: 'An internal server error occurred. Please try again later.',
    503: 'The AI service is temporarily unavailable. Please try again in a moment.',
  };
  return new Error(statusMessages[status] || `Server returned an error (${status}). Please try again.`);
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const detail = error.response && error.response.data && error.response.data.detail;
    if (error.response && error.response.status === 403 && detail === CSRF_FAILURE_DETAIL) {
      try {
        await refreshCsrfToken();
      } catch (_refreshError) {
        // Return the original failed request; callers can retry it themselves.
      }
    } else if (error.response && error.response.status === 401) {
      clearCsrfToken('logout');
    }
    return Promise.reject(normalizeError(error));
  }
);

export default apiClient;
