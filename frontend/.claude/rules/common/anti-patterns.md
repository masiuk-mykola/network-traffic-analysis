---
paths:
  - '**/*.ts'
  - '**/*.tsx'
---

# Anti-Patterns

Do not write code that matches these patterns.

## Logic anti-patterns

### Nested ternaries
```typescript
// WRONG
const label = isLoading ? 'Loading...' : hasError ? 'Error' : data ? data.name : 'Unknown'

// CORRECT
function getLabel(): string {
  if (isLoading) return 'Loading...'
  if (hasError) return 'Error'
  if (data) return data.name
  return 'Unknown'
}
```

### Deep nesting
```typescript
// WRONG — 5 levels deep
if (user) {
  if (user.session) {
    if (user.session.isActive) {
      if (canSendMessage) {
        sendMessage()
      }
    }
  }
}

// CORRECT — early returns
if (!user?.session?.isActive) return
if (!canSendMessage) return
sendMessage()
```

### Magic numbers
```typescript
// WRONG
setTimeout(retryFn, 3000)
if (attempts > 5) throw new Error('Too many retries')

// CORRECT
const RETRY_DELAY_MS = 3_000
const MAX_RETRY_ATTEMPTS = 5
setTimeout(retryFn, RETRY_DELAY_MS)
if (attempts > MAX_RETRY_ATTEMPTS) throw new Error('Too many retries')
```

## React anti-patterns

### State duplication
```typescript
// WRONG — duplicating server state in local state
const [session, setSession] = useState<Session>()
useEffect(() => {
  fetchSession(id).then(setSession)
}, [id])

// CORRECT — use TanStack Query
const { data: session } = useQuery({ queryKey: ['session', id], queryFn: () => fetchSession(id) })
```

### State for derived values
```typescript
// WRONG
const [fullName, setFullName] = useState('')
useEffect(() => setFullName(`${firstName} ${lastName}`), [firstName, lastName])

// CORRECT
const fullName = `${firstName} ${lastName}`
```

### Unstable object references in props
```typescript
// WRONG — new object on every render breaks React.memo
<Component config={{ timeout: 3000 }} />

// CORRECT
const config = useMemo(() => ({ timeout: 3000 }), [])
<Component config={config} />
```

### Index as key
```typescript
// WRONG — breaks state on reorder/delete
{messages.map((msg, i) => <Message key={i} message={msg} />)}

// CORRECT
{messages.map(msg => <Message key={msg.id} message={msg} />)}
```

## TypeScript anti-patterns

### Casting instead of narrowing
```typescript
// WRONG
const user = response.data as User

// CORRECT — validate or assert with a guard
function isUser(value: unknown): value is User {
  return typeof value === 'object' && value !== null && 'id' in value
}
if (isUser(response.data)) { ... }
```

### Any escape hatch
```typescript
// WRONG
function processEvent(event: any) { ... }

// CORRECT
function processEvent(event: unknown) {
  if (!(event instanceof CustomEvent)) return
  // narrow and use
}
```

## Other anti-patterns

- `console.log` left in committed code
- `// @ts-ignore` without a comment explaining why it is necessary
- Async functions that do not handle errors
- Event listeners added without cleanup
- Direct DOM manipulation alongside React state
