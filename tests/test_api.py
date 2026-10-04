"""Integration tests for AgentFlow FastAPI HTTP endpoints and SSE streaming."""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.agent.agent import AgentFlowResult


class TestAPIEndpoints:
    """Tests for /health, /chat, and /chat/stream routes."""

    def test_health_endpoint(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["database_connected"] is True

    @patch("app.api.routes.get_agent")
    def test_chat_endpoint_success(self, mock_get_agent, client: TestClient):
        mock_agent = MagicMock = mock_get_agent.return_value
        mock_agent.achat = AsyncMock(
            return_value=AgentFlowResult(
                answer="Total quarterly sales are $145,000.",
                tools_used=["sql_query"],
                execution_time_ms=350.0,
                trace=[
                    {
                        "step_index": 1,
                        "tool_name": "sql_query",
                        "input_summary": "SELECT sum(net_revenue) FROM sales",
                        "output_summary": "145000.0",
                        "execution_time_ms": 42.0,
                        "status": "success",
                    }
                ],
                token_metrics={"total_tokens": 520, "estimated_cost_usd": 0.0003},
                success=True,
            )
        )

        payload = {"message": "What are our total sales for this quarter?"}
        response = client.post("/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Total quarterly sales are $145,000."
        assert data["tools_used"] == ["sql_query"]
        assert data["execution_time_ms"] == 350.0
        assert len(data["trace"]) == 1
        assert data["token_metrics"]["total_tokens"] == 520

    def test_chat_missing_message_field(self, client: TestClient):
        response = client.post("/chat", json={})
        assert response.status_code == 422

    def test_chat_empty_message(self, client: TestClient):
        response = client.post("/chat", json={"message": ""})
        assert response.status_code == 422

    def test_chat_oversized_message(self, client: TestClient):
        huge_message = "A" * 3000
        response = client.post("/chat", json={"message": huge_message})
        assert response.status_code == 422

    def test_chat_malformed_json(self, client: TestClient):
        response = client.post(
            "/chat",
            content="not a json payload",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    @patch("app.api.routes.get_agent")
    def test_chat_stream_endpoint(self, mock_get_agent, client: TestClient):
        mock_agent = mock_get_agent.return_value

        async def mock_stream(msg, request_id):
            yield {"event": "start", "message": "Planning started"}
            yield {"event": "final_answer", "answer": "Calculated value: 42", "tools_used": []}
            yield {"event": "done", "status": "completed"}

        mock_agent.astream = mock_stream

        response = client.post("/chat/stream", json={"message": "Compute 21 * 2"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body_text = response.text
        assert "data:" in body_text
        assert "Planning started" in body_text
        assert "Calculated value: 42" in body_text
