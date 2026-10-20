import React, { useEffect, useRef, useState } from 'react';
import { API_URL } from './constants';

let activeHeaders = {};
const cache = new Map();
const queue = [];
let active = 0;
const privatePath = (s) => typeof s === 'string' &&
  /^\/api\/(private-media|public\/avatar|public\/chat-photo)\/[a-zA-Z0-9_.-]+$/.test(s);

// Register auth without downloading: an unavailable attachment must never block text/actions.
export function hydrateMedia(value, headers) {
  activeHeaders = headers || {};
  return value;
}

function pump() {
  while (active < 4 && queue.length) {
    active++;
    const { task, resolve, reject } = queue.shift();
    task().then(resolve, reject).finally(() => { active--; pump(); });
  }
}

function download(path, headers, signal, begin) {
  return new Promise((resolve, reject) => {
    queue.push({ resolve, reject, task: async () => {
      if (signal.aborted) throw new Error('Image request cancelled');
      const finish = begin();
      try {
        const mid = path.split('/').pop();
        const response = await fetch(/^\/api\/private-media\//.test(path)
          ? `${API_URL}/api/private-media/${mid}` : API_URL + path, { headers, signal });
        if (!response.ok) throw new Error('تصویر خوانده نشد؛ دسترسی یا اتصال ربات را بررسی کنید');
        const blob = await response.blob();
        if (blob.size > 3 * 1024 * 1024 || !/^image\/(png|jpeg|webp)$/.test(blob.type)) {
          throw new Error('تصویر دریافتی معتبر نیست');
        }
        return await new Promise((done, fail) => {
          const reader = new FileReader();
          reader.onload = () => done(reader.result);
          reader.onerror = () => fail(new Error('تصویر خوانده نشد'));
          reader.readAsDataURL(blob);
        });
      } finally { finish(); }
    } });
    pump();
  });
}

export function PrivateImage({ src, ...props }) {
  const [state, setState] = useState({ key: '', src: '', error: '' });
  const [visibleKey, setVisibleKey] = useState('');
  const element = useRef(null);
  const onError = useRef(props.onError);
  onError.current = props.onError;
  const headers = activeHeaders;
  const key = JSON.stringify(headers) + src;
  const deferred = props.loading === 'lazy' && visibleKey !== key;
  useEffect(() => {
    if (!privatePath(src) || !deferred) return undefined;
    if (typeof IntersectionObserver === 'undefined') { setVisibleKey(key); return undefined; }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setVisibleKey(key); observer.disconnect(); }
    });
    observer.observe(element.current);
    return () => observer.disconnect();
  }, [src, key, deferred]);
  useEffect(() => {
    if (!privatePath(src) || deferred) return undefined;
    const ctl = new AbortController();
    if (cache.has(key)) { setState({ key, src: cache.get(key), error: '' }); return undefined; }
    setState({ key, src: '', error: '' });
    const fail = (error) => {
      setState({ key, src: '', error });
      onError.current?.();
    };
    let timer;
    download(src, headers, ctl.signal, () => {
      timer = setTimeout(() => { fail('دریافت تصویر طول کشید؛ متن و دکمه‌ها قابل استفاده‌اند'); ctl.abort(); }, 20000);
      return () => clearTimeout(timer);
    }).then((data) => {
      if (ctl.signal.aborted) return;
      if (cache.size >= 32) cache.delete(cache.keys().next().value);
      cache.set(key, data); setState({ key, src: data, error: '' });
    }).catch(() => {
      if (!ctl.signal.aborted) fail('تصویر در دسترس نیست؛ متن و دکمه‌ها قابل استفاده‌اند');
    });
    return () => { clearTimeout(timer); ctl.abort(); };
  }, [src, key, deferred]);
  if (!privatePath(src)) return React.createElement('img', { src, ...props });
  if (!state.src || state.key !== key) return React.createElement('span', { role: 'img', 'aria-label': state.error || 'در حال دریافت تصویر',
    ref: element, title: state.error, className: props.className,
    style: { ...props.style, display: 'inline-block', minWidth: props.width || 24, minHeight: props.height || 24 } }, state.error || 'در حال دریافت تصویر…');
  return React.createElement('img', { ...props, ref: element, src: state.src });
}
