/** WebView2 policy is an environment/profile setting, not a per-site cookie flag. */
export function browserProfileNamespace(serviceId: string, assignments: Record<string, string>): string {
  const sandbox = Object.hasOwn(assignments, serviceId) ? assignments[serviceId] : undefined;
  return sandbox ? `sandbox:${sandbox}` : `service:${serviceId}`;
}

export function retainedTrackingExceptions(
  exceptions: Record<string, boolean>, serviceIds: Set<string>, sandboxIds: Set<string>,
): Record<string, boolean> {
  return Object.fromEntries(Object.entries(exceptions).filter(([key]) =>
    key.startsWith("service:") ? serviceIds.has(key.slice(8)) :
      key.startsWith("sandbox:") && sandboxIds.has(key.slice(8))));
}
