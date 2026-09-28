/* Resolve every application-local URL from the document base.
   At / this returns /...; behind the reverse proxy at /smt/ it returns
   /smt/.... Absolute third-party URLs, blobs, data URLs and fragments pass
   through unchanged. */
window.GeoAIApp = (() => {
  const baseUrl = new URL(document.querySelector('base')?.href || './', window.location.href);
  const external = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i;
  const url = value => {
    const text = String(value ?? '');
    if (!text || external.test(text)) return text;
    return `${baseUrl.toString()}${text.replace(/^\/+/, '')}`;
  };
  return { basePath: baseUrl.pathname, baseUrl: baseUrl.toString(), url };
})();
