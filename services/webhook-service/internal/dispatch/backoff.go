package dispatch

import (
	"crypto/rand"
	"math"
	"math/big"
	"time"
)

// Backoff computes the delay before attempt n+1 (n = attempts already made,
// starting at 1): base * 2^(n-1), capped at max. With jitter the result is
// drawn uniformly from [d/2, d].
func Backoff(attempt int, base, max time.Duration, jitter bool) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	exp := float64(base) * math.Pow(2, float64(attempt-1))
	if exp > float64(max) || math.IsInf(exp, 0) {
		exp = float64(max)
	}
	d := time.Duration(exp)
	if jitter && d > 0 {
		half := d / 2
		d = half + time.Duration(randInt63n(int64(half)+1))
	}
	return d
}

func randInt63n(n int64) int64 {
	v, err := rand.Int(rand.Reader, big.NewInt(n))
	if err != nil {
		return n - 1
	}
	return v.Int64()
}
