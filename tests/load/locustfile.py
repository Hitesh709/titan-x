"""Locust load test for TITAN X API.

Usage::

    locust -f tests/load/locustfile.py --host=http://localhost:8000
"""
from __future__ import annotations

import random

from locust import FastHttpUser, between, task


class ApiUser(FastHttpUser):
    wait_time = between(1.0, 3.0)
    api_key = None

    def on_start(self):
        self.api_key = self.environment.parsed_options.api_key if hasattr(self.environment.parsed_options, "api_key") else ""
        self.client.headers.update({"X-API-Key": self.api_key})

    @task(5)
    def health_live(self):
        self.client.get("/health/live", name="/health/live")

    @task(5)
    def health_ready(self):
        self.client.get("/health/ready", name="/health/ready")

    @task(3)
    def version(self):
        self.client.get("/api/v1/version", name="/api/v1/version")

    @task(2)
    def get_companies(self):
        self.client.get("/api/v1/companies?limit=10", name="/api/v1/companies")

    @task(2)
    def get_sectors(self):
        self.client.get("/api/v1/sectors", name="/api/v1/sectors")

    @task(1)
    def get_market_heatmap(self):
        self.client.get("/api/v1/market/heatmap", name="/api/v1/market/heatmap")

    @task(1)
    def get_sector_rotation(self):
        self.client.get("/api/v1/sector-rotation", name="/api/v1/sector-rotation")

    @task(1)
    def get_portfolio(self):
        self.client.get("/api/v1/portfolio", name="/api/v1/portfolio")

    @task(1)
    def search(self):
        self.client.get("/api/v1/search?q=tesla", name="/api/v1/search")

    @task(1)
    def get_dashboard(self):
        self.client.get("/api/v1/dashboard", name="/api/v1/dashboard")

    @task(1)
    def monitoring_system(self):
        self.client.get("/api/v1/monitoring/system", name="/api/v1/monitoring/system")

    @task(1)
    def get_news(self):
        self.client.get("/api/v1/news?limit=5", name="/api/v1/news")


class WriteUser(FastHttpUser):
    """
    Simulates authenticated write operations.
    """

    wait_time = between(5.0, 15.0)

    def on_start(self):
        self.api_key = self.environment.parsed_options.api_key if hasattr(self.environment.parsed_options, "api_key") else ""
        self.client.headers.update({"X-API-Key": self.api_key, "Content-Type": "application/json"})

    @task(1)
    def record_metric(self):
        self.client.post(
            "/api/v1/monitoring/metrics/load_test?value=" + str(random.uniform(10, 100)),
            name="/api/v1/monitoring/metrics/load_test",
        )
