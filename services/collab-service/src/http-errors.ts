import { Response } from 'express';

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    status: number;
  };
}

export function apiErrorResponse(
  status: number,
  code: string,
  message: string,
): ApiErrorResponse {
  return {
    error: {
      code,
      message,
      status,
    },
  };
}

export function sendApiError(
  response: Response,
  status: number,
  code: string,
  message: string,
): Response {
  return response.status(status).json(apiErrorResponse(status, code, message));
}
