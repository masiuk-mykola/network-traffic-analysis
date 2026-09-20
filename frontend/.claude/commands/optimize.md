# /optimize

Analyze and optimize the selected code for performance. Do not change behavior.

## Step 1 — Diagnose first

Before making any changes, identify the actual problem:
- Unnecessary re-renders (missing memoization, unstable references)
- Expensive computations running on every render
- Large bundle chunks that could be lazy-loaded
- Heavy lists without virtualization
- Redundant API calls or missing caching
- Dependency arrays that cause excessive effect runs

## Step 2 — Apply targeted fixes

Only fix what is actually a problem. Do not add memoization everywhere speculatively.

### React rendering
- Wrap expensive child components in `React.memo` only if they receive stable props
- Use `useMemo` for computations that are expensive AND depend on specific values
- Use `useCallback` for functions passed as props to memoized children
- Move static values outside the component body

### Data fetching
- Use TanStack Query `staleTime`/`gcTime` to avoid refetching data that hasn't changed
- Deduplicate requests by sharing query keys
- Use `select` to transform data inside the query instead of in the component

### Bundle
- Lazy-load route-level components and heavy third-party libs with `React.lazy`
- Check imports — avoid importing full libraries when tree-shaking is available

### Lists
- Lists > 100 items: consider virtualization

## Rules

- Measure before optimizing — do not guess
- Do not add complexity for marginal gains
- Document WHY each optimization is needed with a brief inline comment

## Output

List each change with: what was changed, why it helps.
