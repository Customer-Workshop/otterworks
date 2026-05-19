Feature: API Proxy Middleware
  As a security engineer
  I want the Next.js middleware to correctly proxy API requests
  So that the middleware cannot be bypassed (CVE-2025-29927)

  Scenario: API routes are proxied through middleware
    Given I navigate to "/api/v1/health"
    Then the response should not be a Next.js 404

  Scenario: Non-API routes render normally
    Given I am on the login page
    Then I should see an "Email" input field
    And I should see a "Password" input field

  Scenario: Middleware cannot be bypassed with x-middleware-subrequest header
    Given I make a GET request to "/api/v1/documents" with header "x-middleware-subrequest" set to "middleware"
    Then the response should not be a Next.js 404

  Scenario: Unauthorized API access is rejected
    Given I navigate to "/api/v1/documents"
    Then the response status should not be 200
