// Tiny cookie helpers so a generated plan survives reloads (cookie-backed
// results). Values are URL-encoded; no PII is ever stored here.

export function getCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : ''
}

export function setCookie(name, value, maxAgeDays = 30) {
  const maxAge = Math.floor(maxAgeDays * 86400)
  document.cookie = `${name}=${encodeURIComponent(value)}; max-age=${maxAge}; path=/; samesite=lax`
}
