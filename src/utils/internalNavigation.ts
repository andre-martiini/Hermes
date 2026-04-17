export const INTERNAL_NAVIGATION_EVENT = 'hermes:navigate';

export const isInternalAppHref = (href: string): boolean => href.startsWith('/');

export const navigateWithinApp = (href: string): void => {
  if (!isInternalAppHref(href) || typeof window === 'undefined') {
    return;
  }

  const normalizedHref = href.trim() || '/';
  if (`${window.location.pathname}${window.location.search}` === normalizedHref) {
    return;
  }

  window.history.pushState({}, '', normalizedHref);
  window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  window.dispatchEvent(new CustomEvent(INTERNAL_NAVIGATION_EVENT, { detail: { href: normalizedHref } }));
};
