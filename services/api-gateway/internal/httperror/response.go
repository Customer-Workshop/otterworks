package httperror

import (
	"encoding/json"
	"net/http"
)

type response struct {
	Error detail `json:"error"`
}

type detail struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Status  int    `json:"status"`
}

// Write sends a standardized JSON error response.
func Write(w http.ResponseWriter, status int, code, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(response{
		Error: detail{
			Code:    code,
			Message: message,
			Status:  status,
		},
	})
}
