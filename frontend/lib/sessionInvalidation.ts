type Handler = () => void;

const handlers = new Set<Handler>();

export function onSessionInvalidated(handler: Handler) {
  handlers.add(handler);
  return () => handlers.delete(handler);
}

export function invalidateSession() {
  handlers.forEach((handler) => handler());
}
