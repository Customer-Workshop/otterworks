# Report Service Modernization — Impact Analysis

Migration of `services/report-service` from the legacy Java 8 / Spring Boot 2.5 stack to
the recommended stack (Java 17 / Spring Boot 3.2), following the 11 upgrade axes in
[UPGRADE_GUIDE.md](./UPGRADE_GUIDE.md).

## Summary of Changes

| # | Axis | Before | After | Risk |
|---|------|--------|-------|------|
| 1 | Java runtime | 1.8 | 17 (LTS) | Low |
| 2 | Namespace | `javax.*` | `jakarta.*` | Low (mechanical) |
| 3 | Spring Boot | 2.5.14 (EOL) | 3.2.5 | **Medium** |
| 4 | Test framework | JUnit 4 | JUnit 5 (Jupiter) | Low |
| 5 | API docs | SpringFox 3.0.0 (dead project) | springdoc-openapi 2.3.0 | Low |
| 6 | PDF library | iText 5.5.13.3 (AGPL) | OpenPDF 1.3.43 (LGPL) | Low (near drop-in) |
| 7 | Commons Lang | 2.6 (EOL 2011) | commons-lang3 3.14.0 | Low |
| 8 | Commons IO | 2.6 | 2.15.1 | Low |
| 9 | Guava | 28.0-jre (CVEs) | 33.1.0-jre | Low |
| 10 | Apache POI | 4.1.2 | 5.2.5 | Low |
| 11 | Mockito | 3.12.4 | 5.11.0 (+ mockito-junit-jupiter) | Low |

## Detailed Impact by Area

### 1. Build & Runtime (Java 17, Dockerfile, CI)
- `pom.xml`: parent upgraded to `spring-boot-starter-parent:3.2.5`, compiler source/target 17.
- `Dockerfile`: builder image `maven:3.9.6-eclipse-temurin-17`, runtime `eclipse-temurin:17-jre`.
- `.github/workflows/ci.yml`: report-service job now uses Temurin 17.
- **Risk**: none at runtime — no use of removed JDK internals was found.

### 2. javax → jakarta Namespace
- `javax.persistence.*` → `jakarta.persistence.*` (entity `Report`)
- `javax.validation.*` → `jakarta.validation.*` (DTOs, controller `@Valid`)
- `javax.transaction.Transactional` → `jakarta.transaction.Transactional` (`ReportService`)
- **Risk**: low; compile-time verified. No reflection-based javax usage.

### 3. Spring Boot 2.5 → 3.2 (includes Spring Security 6, Hibernate 6)
- `SecurityConfig` rewritten: `WebSecurityConfigurerAdapter` (removed in Security 6) replaced
  by a `SecurityFilterChain` bean; `antMatchers` → `requestMatchers`, `authorizeRequests` →
  `authorizeHttpRequests`, lambda-style DSL for headers/CSRF/session management.
- `AppConfig` RestTemplate now uses Apache HttpClient 5 (`org.apache.hc.client5`)
  — HttpClient 4 is no longer supported by Spring 6's `HttpComponentsClientHttpRequestFactory`.
  Connect/read timeouts moved to `ConnectionConfig` on the pooling connection manager.
- Hibernate 6: `ddl-auto=update` schema behavior verified against H2 (tests) — PostgreSQL
  production schema is compatible (no enum/date column type changes needed).
- Removed `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` workaround
  (only needed for SpringFox).
- **Risk**: medium — largest behavioral surface (security filter chain, Hibernate 6 SQL
  generation). Mitigated by full integration test suite against H2 and E2E tests.

### 4. JUnit 4 → 5
- All tests migrated: `@RunWith(SpringRunner.class)` removed, `@Before/@After` →
  `@BeforeEach/@AfterEach`, `org.junit.Assert` → `org.junit.jupiter.api.Assertions`
  (message argument moved last).
- **Risk**: low; 71 tests green.

### 5. SpringFox → springdoc-openapi
- `SwaggerConfig` rewritten as an `OpenAPI` bean; SpringFox `Docket` removed.
- Annotations replaced: `@Api` → `@Tag`, `@ApiOperation` → `@Operation`,
  `@ApiParam` → `@Parameter`, `@ApiResponse(code=…)` → `@ApiResponse(responseCode=…)`,
  `@ApiModel/@ApiModelProperty` → `@Schema`.
- Docs now at `/v3/api-docs` and `/swagger-ui.html` (added to security allow-list).
- **Consumer impact**: the old `/v2/api-docs` and `/swagger-ui/` SpringFox URLs are gone.

### 6. iText 5 → OpenPDF
- Dependency swap: `com.itextpdf:itextpdf:5.5.13.3` → `com.github.librepdf:openpdf:1.3.43`.
- Package rename `com.itextpdf.text.*` → `com.lowagie.text.*`; `BaseColor` → `java.awt.Color`;
  `Font.FontFamily.HELVETICA` → `Font.HELVETICA`.
- **License impact**: removes AGPL exposure (OpenPDF is LGPL/MPL).
- Output verified byte-level by unit tests (PDF magic bytes, parseable structure).

### 7–10. Commons Lang 3, Commons IO, Guava, POI
- `org.apache.commons.lang.*` → `org.apache.commons.lang3.*` (StringUtils, DateUtils,
  DateFormatUtils — API compatible for all call sites used here).
- Guava 28 → 33 fixes known CVEs (e.g. CVE-2020-8908, CVE-2023-2976); `LoadingCache` API unchanged.
- POI 4.1.2 → 5.2.5: `XSSFWorkbook` API stable for the generator's usage.
- Commons IO 2.6 → 2.15.1: `FileUtils.readFileToByteArray` unchanged.

### 11. Mockito 3 → 5
- `mockito-core` 5.11.0 + `mockito-junit-jupiter` for `@ExtendWith(MockitoExtension.class)`.
- Mockito 5 uses the inline mock maker by default (works on JDK 17 without `--add-opens`).

## What Did NOT Change
- Public REST API surface (`/api/v1/reports` CRUD + `/download`) — request/response
  JSON is byte-compatible; API-gateway routing unaffected.
- Database schema: column names, types, and table layout are unchanged. One entity
  annotation did change: `error_message` was `@Lob` (Hibernate 5 → `text` on PostgreSQL)
  and is now `@Column(columnDefinition = "TEXT")`, because Hibernate 6 maps `@Lob String`
  to `oid`, which breaks `ddl-auto=update` against the existing `text` column. The
  resulting DDL is the same `text` type, so no data migration is needed.
- Report file formats and content (PDF/CSV/Excel generators produce identical output).
- Remaining tech debt intentionally out of scope for this migration (tracked in code
  comments): `java.util.Date` → `java.time`, RestTemplate → RestClient/WebClient,
  Guava cache → Caffeine, streaming downloads instead of `ByteArrayResource`.

## Test Coverage

| Level | Location | What it verifies |
|-------|----------|------------------|
| Unit (JUnit 5) | `src/test/java/.../service/*GeneratorTest` | PDF/CSV/Excel file structure, magic bytes, content |
| Unit (Mockito 5) | `src/test/java/.../service/ReportServiceUnitTest` | orchestration, deferred async-after-commit, delete semantics |
| Unit (JUnit 5) | `src/test/java/.../util/ReportDateUtilsTest` | date formatting/parsing/ranges |
| Integration | `src/test/java/.../controller/ReportControllerIntegrationTest`, `ReportServiceTest` | full Spring context + H2, HTTP status codes, validation |
| Playwright E2E | `frontend/web-app/e2e/reports-api.spec.ts` | live-service report generation + download for all three formats |

`mvn test`: 71 tests, 0 failures.

## Rollback Plan
Single-commit revert restores the legacy stack; no data migration is involved
(schema unchanged), so rollback is safe at any time.
