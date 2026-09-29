// On-sale load: ONE k6 script that fires the same purchase storm at the before host (monolith) and the after
// host (services) at the same time, through the shared ingress. Runs in-cluster as a Job (see run-onsale.sh).
//
// Shape (all env, per side): RAMP (time to reach PEAK), PEAK (orders per minute), DURATION (time held at
// PEAK), RAMPDOWN (time back to 0). Every request carries a unique order key
// <RUN_ID>-<side>-<n> as clientRef, X-Order-Key and in the customer email, so fired orders can be reconciled
// against each side's /api/stats and order records afterwards.
//
// The summary (fired per side, status counts, latency percentiles) is printed between
// "=== ONSALE_SUMMARY_BEGIN ===" / "=== ONSALE_SUMMARY_END ===" markers; run-onsale.sh stores it as a file
// under ticketing/.runs/<token>/ and as ConfigMap <token>-onsale-summary in <token>-after.
import http from 'k6/http';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';

const RUN_ID = __ENV.RUN_ID || 'local';
const TOKEN = __ENV.TOKEN || 'tkt';
const RAMP = __ENV.RAMP || '60s';
const PEAK = parseInt(__ENV.PEAK || '600', 10);          // orders per minute per side
const DURATION = __ENV.DURATION || '120s';
const RAMPDOWN = __ENV.RAMPDOWN || '30s';
const MAX_VUS = parseInt(__ENV.MAX_VUS || '300', 10);
const PERFORMANCES = parseInt(__ENV.PERFORMANCES || '24', 10);
const QUANTITY = parseInt(__ENV.QUANTITY || '2', 10);
const HOSTS = {
  before: __ENV.BEFORE_HOST || `${TOKEN}-before.demo.otterworks.app`,
  after: __ENV.AFTER_HOST || `${TOKEN}-after.demo.otterworks.app`,
};
const SIDES = ['before', 'after'];
const CODES = ['200', '201', '202', '400', '402', '404', '409', '410', '429', '500', '502', '503', '504', '0'];

function stages() {
  return [
    { duration: RAMP, target: PEAK },
    { duration: DURATION, target: PEAK },
    { duration: RAMPDOWN, target: 0 },
  ];
}
function scenario(side) {
  return {
    executor: 'ramping-arrival-rate',
    exec: side,
    startRate: 0,
    timeUnit: '1m',
    preAllocatedVUs: Math.min(50, MAX_VUS),
    maxVUs: MAX_VUS,
    stages: stages(),
    tags: { side },
  };
}

export const options = {
  scenarios: { before: scenario('before'), after: scenario('after') },
  thresholds: {
    'http_req_duration{side:before}': ['p(95)<120000'],
    'http_req_duration{side:after}': ['p(95)<120000'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  insecureSkipTLSVerify: true,   // scratch image: no CA bundle; traffic still enters through the shared ingress
  discardResponseBodies: false,
  userAgent: `ticketing-onsale/${RUN_ID}`,
};

const fired = {}, accepted = {}, latency = {}, statuses = {};
for (const side of SIDES) {
  fired[side] = new Counter(`fired_${side}`);
  accepted[side] = new Counter(`accepted_${side}`);
  latency[side] = new Trend(`latency_${side}`, true);
  statuses[side] = {};
  for (const c of CODES.concat(['other'])) statuses[side][c] = new Counter(`status_${side}_${c}`);
}

function purchase(side) {
  const n = exec.scenario.iterationInTest;
  const key = `${RUN_ID}-${side}-${String(n).padStart(6, '0')}`;
  const body = JSON.stringify({
    performanceId: 1 + (n % PERFORMANCES),
    email: `k6-${key}@example.test`,
    quantity: QUANTITY,
    cardLast4: '4242',
    delivery: 'MOBILE',
    clientRef: key,
  });
  const res = http.post(`https://${HOSTS[side]}/api/purchase`, body, {
    headers: { 'Content-Type': 'application/json', 'X-Order-Key': key },
    tags: { side, name: `purchase-${side}` },
    timeout: '60s',
  });
  fired[side].add(1);
  latency[side].add(res.timings.duration);
  const code = String(res.status);
  (statuses[side][code] || statuses[side].other).add(1);
  if (res.status === 201 || res.status === 202) accepted[side].add(1);   // monolith 201 CONFIRMED; services 202 PENDING_PAYMENT
}

export function before() { purchase('before'); }
export function after() { purchase('after'); }

function metricValue(data, name, stat) {
  const m = data.metrics[name];
  return m && m.values && m.values[stat] !== undefined ? m.values[stat] : 0;
}

export function handleSummary(data) {
  const sides = {};
  for (const side of SIDES) {
    const st = {};
    for (const c of CODES.concat(['other'])) {
      const v = metricValue(data, `status_${side}_${c}`, 'count');
      if (v > 0) st[c] = v;
    }
    sides[side] = {
      host: HOSTS[side],
      fired: metricValue(data, `fired_${side}`, 'count'),
      accepted: metricValue(data, `accepted_${side}`, 'count'),
      statuses: st,
      latency_ms: {
        avg: Math.round(metricValue(data, `latency_${side}`, 'avg')),
        p50: Math.round(metricValue(data, `latency_${side}`, 'med')),
        p90: Math.round(metricValue(data, `latency_${side}`, 'p(90)')),
        p95: Math.round(metricValue(data, `latency_${side}`, 'p(95)')),
        p99: Math.round(metricValue(data, `latency_${side}`, 'p(99)')),
        max: Math.round(metricValue(data, `latency_${side}`, 'max')),
      },
    };
  }
  const summary = {
    run_id: RUN_ID,
    token: TOKEN,
    finished_at: new Date().toISOString(),
    test_duration_s: Math.round((data.state.testRunDurationMs || 0) / 1000),
    shape: { ramp: RAMP, peak_orders_per_minute: PEAK, duration: DURATION, rampdown: RAMPDOWN, max_vus: MAX_VUS,
             performances: PERFORMANCES, quantity: QUANTITY },
    order_key_pattern: `${RUN_ID}-<side>-<n>`,
    dropped_iterations: metricValue(data, 'dropped_iterations', 'count'),
    http_reqs: metricValue(data, 'http_reqs', 'count'),
    sides,
  };
  const lines = [`on-sale ${RUN_ID}: peak ${PEAK}/min per side, ramp ${RAMP}, hold ${DURATION}, rampdown ${RAMPDOWN}`];
  for (const side of SIDES) {
    const s = sides[side];
    lines.push(`  ${side.padEnd(6)} fired=${s.fired} accepted=${s.accepted} p50=${s.latency_ms.p50}ms p95=${s.latency_ms.p95}ms ` +
               `max=${s.latency_ms.max}ms statuses=${JSON.stringify(s.statuses)}`);
  }
  lines.push(`  dropped_iterations=${summary.dropped_iterations} (arrival rate not met: all ${MAX_VUS} VUs busy)`);
  return {
    stdout: lines.join('\n') + '\n=== ONSALE_SUMMARY_BEGIN ===\n' + JSON.stringify(summary, null, 2) + '\n=== ONSALE_SUMMARY_END ===\n',
  };
}
