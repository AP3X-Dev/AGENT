export function isStandaloneUi(): boolean {
  // Standalone mode defaults to OFF for real AG3NT backend integration.
  // Set `NEXT_PUBLIC_STANDALONE_UI=true` to force standalone behavior.
  return process.env.NEXT_PUBLIC_STANDALONE_UI === "true"
}
