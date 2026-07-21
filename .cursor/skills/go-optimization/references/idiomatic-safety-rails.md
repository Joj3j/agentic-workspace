# Idiomatic concurrency and allocation safety rails

## errgroup + semaphore (I/O fan-out)

**Instead of** N worker goroutines draining `chan Job`:

```go
g, ctx := errgroup.WithContext(ctx)
sem := semaphore.NewWeighted(int64(maxConcurrent))
for _, job := range jobs {
    job := job
    g.Go(func() error {
        if err := sem.Acquire(ctx, 1); err != nil {
            return err
        }
        defer sem.Release(1)
        return doIO(ctx, job)
    })
}
if err := g.Wait(); err != nil {
    return err
}
```

- First error cancels sibling work via `ctx`.
- Semaphore bounds NE/FD budget without a permanent pool.

## When custom pools hurt

- I/O-bound work: scheduling overhead of pools rarely beats direct goroutines + semaphore.
- Pools hide backpressure — document queue depth if you must use a channel buffer.

## sync.Map decision tree

Use `sync.Map` when:

- Keys inserted once, read many (config snapshots), or
- Goroutines use disjoint key sets.

Use `RWMutex` + `map` when:

- Mixed read/write on same keys (subscription registry, NE index).

## Read-mostly config

`atomic.Pointer[Config]` or `atomic.Value` for swap-on-update; readers avoid locks.

## sync.Pool

Only when benchmarks show repeated allocation of same-sized buffers (e.g. encode buffers).
Always `Put` with reset state; do not pool objects holding pointers to request-scoped data.

## Logging on hot paths

zerolog chain without `Msgf` on protos:

```go
logger.Debug().Str("neId", neID).Int("n", len(paths)).Msg("merge")
```
