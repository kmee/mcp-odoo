"""
Tests for the Odoo XML-RPC client
"""

import json
import os
import socket
import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
import xmlrpc.client


class TestOdooClientInit:
    """Tests for OdooClient initialization"""

    def test_init_with_http_url(self, mock_xmlrpc_server, mock_odoo_config):
        """Test initialization with HTTP URL"""
        from odoo_mcp.odoo_client import OdooClient

        config = mock_odoo_config.copy()
        config["url"] = "http://test-odoo.example.com"

        client = OdooClient(
            url=config["url"],
            db=config["db"],
            username=config["username"],
            password=config["password"],
        )

        assert client.url == "http://test-odoo.example.com"
        assert client.db == config["db"]
        assert client.username == config["username"]
        assert client.uid == 1

    def test_init_with_https_url(self, mock_xmlrpc_server, mock_odoo_config):
        """Test initialization with HTTPS URL"""
        from odoo_mcp.odoo_client import OdooClient

        client = OdooClient(
            url=mock_odoo_config["url"],
            db=mock_odoo_config["db"],
            username=mock_odoo_config["username"],
            password=mock_odoo_config["password"],
        )

        assert client.url == "https://test-odoo.example.com"
        assert client.uid == 1

    def test_init_without_protocol(self, mock_xmlrpc_server, mock_odoo_config):
        """Test initialization adds http:// if no protocol specified"""
        from odoo_mcp.odoo_client import OdooClient

        config = mock_odoo_config.copy()
        config["url"] = "test-odoo.example.com"

        client = OdooClient(
            url=config["url"],
            db=config["db"],
            username=config["username"],
            password=config["password"],
        )

        assert client.url == "http://test-odoo.example.com"

    def test_init_removes_trailing_slash(self, mock_xmlrpc_server, mock_odoo_config):
        """Test initialization removes trailing slash from URL"""
        from odoo_mcp.odoo_client import OdooClient

        config = mock_odoo_config.copy()
        config["url"] = "https://test-odoo.example.com/"

        client = OdooClient(
            url=config["url"],
            db=config["db"],
            username=config["username"],
            password=config["password"],
        )

        assert client.url == "https://test-odoo.example.com"

    def test_init_authentication_failed(self, mock_xmlrpc_server, mock_odoo_config):
        """Test initialization fails when authentication returns None"""
        from odoo_mcp.odoo_client import OdooClient

        mock_xmlrpc_server["common"].authenticate.return_value = None

        with pytest.raises(ValueError, match="Authentication failed"):
            OdooClient(
                url=mock_odoo_config["url"],
                db=mock_odoo_config["db"],
                username=mock_odoo_config["username"],
                password=mock_odoo_config["password"],
            )

    def test_init_connection_error(self, mock_odoo_config):
        """Test initialization handles connection errors"""
        from odoo_mcp.odoo_client import OdooClient

        with patch("xmlrpc.client.ServerProxy") as mock_server:
            mock_common = MagicMock()
            mock_common.authenticate.side_effect = socket.timeout("Connection timed out")

            def get_proxy(url, **kwargs):
                if "/common" in url:
                    return mock_common
                return MagicMock()

            mock_server.side_effect = get_proxy

            with pytest.raises(ConnectionError, match="Failed to connect"):
                OdooClient(
                    url=mock_odoo_config["url"],
                    db=mock_odoo_config["db"],
                    username=mock_odoo_config["username"],
                    password=mock_odoo_config["password"],
                )


class TestOdooClientGetModels:
    """Tests for get_models method"""

    def test_get_models_success(self, mock_odoo_client, sample_models_data):
        """Test successful retrieval of models"""
        mock_odoo_client._models.execute_kw.side_effect = [
            [1, 2, 3, 4],  # search returns IDs
            sample_models_data,  # read returns model data
        ]

        result = mock_odoo_client.get_models()

        assert "model_names" in result
        assert "models_details" in result
        assert "res.partner" in result["model_names"]
        assert "hr.employee" in result["model_names"]
        assert len(result["model_names"]) == 4

    def test_get_models_empty(self, mock_odoo_client):
        """Test get_models when no models found"""
        mock_odoo_client._models.execute_kw.return_value = []

        result = mock_odoo_client.get_models()

        assert result["model_names"] == []
        assert "error" in result

    def test_get_models_error(self, mock_odoo_client):
        """Test get_models handles exceptions"""
        mock_odoo_client._models.execute_kw.side_effect = Exception("Network error")

        result = mock_odoo_client.get_models()

        assert "error" in result
        assert "Network error" in result["error"]


class TestOdooClientGetModelInfo:
    """Tests for get_model_info method"""

    def test_get_model_info_success(self, mock_odoo_client):
        """Test successful retrieval of model info"""
        mock_odoo_client._models.execute_kw.return_value = [
            {"id": 1, "name": "Contact", "model": "res.partner"}
        ]

        result = mock_odoo_client.get_model_info("res.partner")

        assert result["name"] == "Contact"
        assert result["model"] == "res.partner"

    def test_get_model_info_not_found(self, mock_odoo_client):
        """Test get_model_info when model not found"""
        mock_odoo_client._models.execute_kw.return_value = []

        result = mock_odoo_client.get_model_info("nonexistent.model")

        assert "error" in result
        assert "not found" in result["error"]

    def test_get_model_info_error(self, mock_odoo_client):
        """Test get_model_info handles exceptions"""
        mock_odoo_client._models.execute_kw.side_effect = Exception("Access denied")

        result = mock_odoo_client.get_model_info("res.partner")

        assert "error" in result


class TestOdooClientGetModelFields:
    """Tests for get_model_fields method"""

    def test_get_model_fields_success(self, mock_odoo_client, sample_fields_data):
        """Test successful retrieval of field definitions"""
        mock_odoo_client._models.execute_kw.return_value = sample_fields_data

        result = mock_odoo_client.get_model_fields("res.partner")

        assert "name" in result
        assert result["name"]["type"] == "char"
        assert result["email"]["type"] == "char"
        assert result["is_company"]["type"] == "boolean"

    def test_get_model_fields_error(self, mock_odoo_client):
        """Test get_model_fields handles exceptions"""
        mock_odoo_client._models.execute_kw.side_effect = Exception("Model not found")

        result = mock_odoo_client.get_model_fields("invalid.model")

        assert "error" in result


class TestOdooClientSearchRead:
    """Tests for search_read method"""

    def test_search_read_success(self, mock_odoo_client, sample_partner_records):
        """Test successful search_read operation"""
        mock_odoo_client._models.execute_kw.return_value = sample_partner_records

        result = mock_odoo_client.search_read(
            "res.partner",
            [("is_company", "=", True)],
            fields=["name", "email"],
            limit=10,
        )

        assert len(result) == 3
        assert result[0]["name"] == "Test Company"

    def test_search_read_with_order(self, mock_odoo_client, sample_partner_records):
        """Test search_read with order parameter"""
        mock_odoo_client._models.execute_kw.return_value = sample_partner_records

        result = mock_odoo_client.search_read(
            "res.partner",
            [],
            order="name ASC",
        )

        assert len(result) == 3

    def test_search_read_empty_result(self, mock_odoo_client):
        """Test search_read returns empty list when no matches"""
        mock_odoo_client._models.execute_kw.return_value = []

        result = mock_odoo_client.search_read(
            "res.partner",
            [("name", "=", "NonexistentName")],
        )

        assert result == []

    def test_search_read_error(self, mock_odoo_client):
        """Test search_read handles exceptions"""
        mock_odoo_client._models.execute_kw.side_effect = Exception("Invalid domain")

        result = mock_odoo_client.search_read("res.partner", [("invalid",)])

        assert result == []


class TestOdooClientReadRecords:
    """Tests for read_records method"""

    def test_read_records_success(self, mock_odoo_client, sample_partner_records):
        """Test successful read of records by ID"""
        mock_odoo_client._models.execute_kw.return_value = [sample_partner_records[0]]

        result = mock_odoo_client.read_records("res.partner", [1])

        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_read_records_multiple(self, mock_odoo_client, sample_partner_records):
        """Test reading multiple records"""
        mock_odoo_client._models.execute_kw.return_value = sample_partner_records

        result = mock_odoo_client.read_records("res.partner", [1, 2, 3])

        assert len(result) == 3

    def test_read_records_with_fields(self, mock_odoo_client):
        """Test read_records with specific fields"""
        mock_odoo_client._models.execute_kw.return_value = [
            {"id": 1, "name": "Test"}
        ]

        result = mock_odoo_client.read_records(
            "res.partner",
            [1],
            fields=["name"],
        )

        assert result[0]["name"] == "Test"

    def test_read_records_error(self, mock_odoo_client):
        """Test read_records handles exceptions"""
        mock_odoo_client._models.execute_kw.side_effect = Exception("Record not found")

        result = mock_odoo_client.read_records("res.partner", [99999])

        assert result == []


class TestOdooClientExecuteMethod:
    """Tests for execute_method"""

    def test_execute_method_success(self, mock_odoo_client):
        """Test successful execution of custom method"""
        mock_odoo_client._models.execute_kw.return_value = {"result": "success"}

        result = mock_odoo_client.execute_method(
            "res.partner",
            "custom_method",
            [1, 2, 3],
            key="value",
        )

        assert result == {"result": "success"}

    def test_execute_method_name_search(self, mock_odoo_client, sample_employee_data):
        """Test name_search method execution"""
        mock_odoo_client._models.execute_kw.return_value = sample_employee_data

        result = mock_odoo_client.execute_method(
            "hr.employee",
            "name_search",
            name="John",
            limit=10,
        )

        assert len(result) == 3
        assert result[0][1] == "John Doe"


class TestRedirectTransport:
    """Tests for RedirectTransport class"""

    def test_transport_init_https(self):
        """Test transport initialization for HTTPS"""
        from odoo_mcp.odoo_client import RedirectTransport

        transport = RedirectTransport(
            timeout=30,
            use_https=True,
            verify_ssl=True,
        )

        assert transport.timeout == 30
        assert transport.use_https is True
        assert transport.verify_ssl is True

    def test_transport_init_no_ssl_verify(self):
        """Test transport initialization without SSL verification"""
        from odoo_mcp.odoo_client import RedirectTransport

        transport = RedirectTransport(
            timeout=30,
            use_https=True,
            verify_ssl=False,
        )

        assert transport.verify_ssl is False
        assert hasattr(transport, "context")

    def test_transport_with_proxy(self, monkeypatch):
        """Test transport initialization with proxy"""
        from odoo_mcp.odoo_client import RedirectTransport

        monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.com:8080")

        transport = RedirectTransport(timeout=30)

        assert transport.proxy == "http://proxy.example.com:8080"


class TestLoadConfig:
    """Tests for load_config function"""

    def test_load_config_from_env(self, mock_env_config):
        """Test loading config from environment variables"""
        from odoo_mcp.odoo_client import load_config

        config = load_config()

        assert config["url"] == "https://env-odoo.example.com"
        assert config["db"] == "env_db"
        assert config["username"] == "env_user"
        assert config["password"] == "env_password"

    def test_load_config_from_file(self, tmp_path, monkeypatch):
        """Test loading config from JSON file"""
        from odoo_mcp.odoo_client import load_config

        # Clear env vars
        for var in ["ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_PASSWORD"]:
            monkeypatch.delenv(var, raising=False)

        # Create config file
        config_data = {
            "url": "https://file-odoo.example.com",
            "db": "file_db",
            "username": "file_user",
            "password": "file_password",
        }
        config_file = tmp_path / "odoo_config.json"
        config_file.write_text(json.dumps(config_data))

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        config = load_config()

        assert config["url"] == "https://file-odoo.example.com"

    def test_load_config_not_found(self, monkeypatch, tmp_path):
        """Test load_config raises error when no config found"""
        from odoo_mcp.odoo_client import load_config

        # Clear env vars
        for var in ["ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_PASSWORD"]:
            monkeypatch.delenv(var, raising=False)

        # Change to empty temp directory
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="No Odoo configuration found"):
            load_config()


class TestGetOdooClient:
    """Tests for get_odoo_client function"""

    def test_get_odoo_client_success(self, mock_env_config, mock_xmlrpc_server):
        """Test successful client creation"""
        from odoo_mcp.odoo_client import get_odoo_client

        client = get_odoo_client()

        assert client is not None
        assert client.uid == 1

    def test_get_odoo_client_with_custom_timeout(
        self, mock_env_config, mock_xmlrpc_server, monkeypatch
    ):
        """Test client creation with custom timeout"""
        from odoo_mcp.odoo_client import get_odoo_client

        monkeypatch.setenv("ODOO_TIMEOUT", "120")

        client = get_odoo_client()

        assert client.timeout == 120

    def test_get_odoo_client_ssl_disabled(
        self, mock_env_config, mock_xmlrpc_server, monkeypatch
    ):
        """Test client creation with SSL verification disabled"""
        from odoo_mcp.odoo_client import get_odoo_client

        monkeypatch.setenv("ODOO_VERIFY_SSL", "0")

        client = get_odoo_client()

        assert client.verify_ssl is False
