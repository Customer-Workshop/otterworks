import { apiErrorResponse } from '../http-errors';

describe('apiErrorResponse', () => {
  it('creates the standard error response shape', () => {
    expect(apiErrorResponse(404, 'NOT_FOUND', 'Route not found')).toEqual({
      error: {
        code: 'NOT_FOUND',
        message: 'Route not found',
        status: 404,
      },
    });
  });
});
