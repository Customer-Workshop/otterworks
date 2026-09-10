package dispatch

import (
	"math"
	"math/rand"
	"time"
)

// Backoff computes the delay before attempt n+1 (n = attempts already made,
// starting at 1): base * 2^(n-1), with full jitter, capped at max.
func Backoff(attempt int, base, max time.Duration, rng *rand.Rand) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	exp := float64(base) * math.Pow(2, float64(attempt-1))
	if exp > float64(max) || math.IsInf(exp, 0) {
		exp = float64(max)
	}
	d := time.Duration(exp)
	if rng != nil && d > 0 {
		// full jitter in [d/2, d]
		half := d / 2
		d = half + time.Duration(rng.Int63n(int64(half)+1))
	}
	return d
}
