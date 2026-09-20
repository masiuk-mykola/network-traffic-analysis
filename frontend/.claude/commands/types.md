# /types

Audit and improve TypeScript types in the selected file(s).

## What to check

### Remove unsafe patterns
- Replace every `any` with `unknown`, a proper type, or a generic
- Replace `as SomeType` casts that could fail at runtime with proper guards
- Remove `@ts-ignore` and `@ts-expect-error` where fixable

### Strengthen types
- Extract repeated inline shapes into named `interface` or `type`
- Replace `object` or `{}` with specific interfaces
- Replace `string | number | boolean` catch-alls with discriminated unions where appropriate
- Add return types to all exported functions

### Use utility types
- `Partial<T>` for optional update payloads
- `Pick<T, K>` / `Omit<T, K>` instead of re-declaring subsets manually
- `Record<K, V>` for key-value maps
- `NonNullable<T>` to strip null/undefined from a type

### Generics
- Make repeated patterns generic instead of duplicating per type
- Constrain generics with `extends` when the type must have certain fields
- Do not use generics where a specific type would be clearer

### React-specific
- Props interface named `{ComponentName}Props`
- Event handler types: `React.ChangeEvent<HTMLInputElement>`, `React.FormEvent`, etc.
- `useRef` generics: `useRef<HTMLDivElement>(null)`
- Context typed with explicit interface; never `any` in `createContext`

## Rules

- Do not change runtime behavior — types only
- Do not add types to private internals that TypeScript already infers correctly
- Keep types co-located with the code that uses them unless shared across files

## Output

List each change with the original type and the replacement.
