import { readDemoList } from './demoData.js';
import { useLoad } from './useLoad.js';

export function useDataSource(token, demoMode, dataset, realLoader, dependencies = []) {
  const loader = demoMode ? () => readDemoList(dataset) : realLoader;
  return useLoad(loader, [token, demoMode, ...dependencies], demoMode ? 0 : undefined);
}
