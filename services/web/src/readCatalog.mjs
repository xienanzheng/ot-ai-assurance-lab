// Retry read-only startup catalogues; never retry control or inference requests.
export async function readCatalog(read, delayMs = 1500) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try { return await read(); }
    catch (error) {
      if (attempt === 2) throw error;
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
}
