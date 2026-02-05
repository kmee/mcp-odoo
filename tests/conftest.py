"""
Pytest configuration and fixtures for odoo-mcp tests
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch


@pytest.fixture
def mock_odoo_config():
    """Sample Odoo configuration for testing"""
    return {
        "url": "https://test-odoo.example.com",
        "db": "test_db",
        "username": "test_user",
        "password": "test_password",
    }


@pytest.fixture
def mock_env_config(monkeypatch):
    """Set up environment variables for Odoo configuration"""
    monkeypatch.setenv("ODOO_URL", "https://env-odoo.example.com")
    monkeypatch.setenv("ODOO_DB", "env_db")
    monkeypatch.setenv("ODOO_USERNAME", "env_user")
    monkeypatch.setenv("ODOO_PASSWORD", "env_password")
    monkeypatch.setenv("ODOO_TIMEOUT", "60")
    monkeypatch.setenv("ODOO_VERIFY_SSL", "1")


@pytest.fixture
def mock_xmlrpc_server():
    """Mock XML-RPC ServerProxy for testing"""
    with patch("xmlrpc.client.ServerProxy") as mock_server:
        # Create mock common and models endpoints
        mock_common = MagicMock()
        mock_models = MagicMock()

        # Configure authenticate to return a user ID
        mock_common.authenticate.return_value = 1

        # Configure the mock to return different proxies based on URL
        def get_proxy(url, **kwargs):
            if "/common" in url:
                return mock_common
            elif "/object" in url:
                return mock_models
            return MagicMock()

        mock_server.side_effect = get_proxy

        yield {
            "server": mock_server,
            "common": mock_common,
            "models": mock_models,
        }


@pytest.fixture
def mock_odoo_client(mock_xmlrpc_server, mock_odoo_config):
    """Create a mocked OdooClient instance"""
    from odoo_mcp.odoo_client import OdooClient

    client = OdooClient(
        url=mock_odoo_config["url"],
        db=mock_odoo_config["db"],
        username=mock_odoo_config["username"],
        password=mock_odoo_config["password"],
        timeout=30,
        verify_ssl=True,
    )
    client._models = mock_xmlrpc_server["models"]
    return client


@pytest.fixture
def sample_models_data():
    """Sample model data returned by Odoo"""
    return [
        {"id": 1, "model": "res.partner", "name": "Contact"},
        {"id": 2, "model": "res.users", "name": "Users"},
        {"id": 3, "model": "sale.order", "name": "Sales Order"},
        {"id": 4, "model": "hr.employee", "name": "Employee"},
    ]


@pytest.fixture
def sample_fields_data():
    """Sample field definitions returned by Odoo"""
    return {
        "id": {
            "type": "integer",
            "string": "ID",
            "readonly": True,
        },
        "name": {
            "type": "char",
            "string": "Name",
            "required": True,
        },
        "email": {
            "type": "char",
            "string": "Email",
            "required": False,
        },
        "is_company": {
            "type": "boolean",
            "string": "Is a Company",
            "required": False,
        },
        "partner_id": {
            "type": "many2one",
            "string": "Related Partner",
            "relation": "res.partner",
        },
    }


@pytest.fixture
def sample_partner_records():
    """Sample partner records returned by Odoo"""
    return [
        {
            "id": 1,
            "name": "Test Company",
            "email": "test@company.com",
            "is_company": True,
        },
        {
            "id": 2,
            "name": "John Doe",
            "email": "john@example.com",
            "is_company": False,
        },
        {
            "id": 3,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "is_company": False,
        },
    ]


@pytest.fixture
def sample_employee_data():
    """Sample employee data for name_search results"""
    return [
        [1, "John Doe"],
        [2, "Jane Smith"],
        [3, "Bob Johnson"],
    ]


@pytest.fixture
def sample_holidays_data():
    """Sample holidays data returned by Odoo"""
    return [
        {
            "id": 1,
            "display_name": "Vacation - John Doe",
            "start_datetime": "2024-01-15 08:00:00",
            "stop_datetime": "2024-01-19 17:00:00",
            "employee_id": [1, "John Doe"],
            "name": "Vacation",
            "state": "validate",
        },
        {
            "id": 2,
            "display_name": "Sick Leave - Jane Smith",
            "start_datetime": "2024-01-10 08:00:00",
            "stop_datetime": "2024-01-11 17:00:00",
            "employee_id": [2, "Jane Smith"],
            "name": "Sick Leave",
            "state": "validate",
        },
    ]
