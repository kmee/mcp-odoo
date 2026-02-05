"""
Tests for the MCP server implementation
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime


class TestMCPResources:
    """Tests for MCP resource endpoints"""

    def test_get_models_resource(self, mock_env_config, mock_xmlrpc_server, sample_models_data):
        """Test the odoo://models resource"""
        from odoo_mcp.server import get_models

        mock_xmlrpc_server["models"].execute_kw.side_effect = [
            [1, 2, 3, 4],
            sample_models_data,
        ]

        result = get_models()
        data = json.loads(result)

        assert "model_names" in data
        assert "res.partner" in data["model_names"]

    def test_get_model_info_resource(self, mock_env_config, mock_xmlrpc_server, sample_fields_data):
        """Test the odoo://model/{model_name} resource"""
        from odoo_mcp.server import get_model_info

        mock_xmlrpc_server["models"].execute_kw.side_effect = [
            [{"id": 1, "name": "Contact", "model": "res.partner"}],
            sample_fields_data,
        ]

        result = get_model_info("res.partner")
        data = json.loads(result)

        assert data["name"] == "Contact"
        assert "fields" in data
        assert "name" in data["fields"]

    def test_get_model_info_not_found(self, mock_env_config, mock_xmlrpc_server):
        """Test get_model_info with non-existent model"""
        from odoo_mcp.server import get_model_info

        mock_xmlrpc_server["models"].execute_kw.return_value = []

        result = get_model_info("nonexistent.model")
        data = json.loads(result)

        assert "error" in data

    def test_get_record_resource(self, mock_env_config, mock_xmlrpc_server, sample_partner_records):
        """Test the odoo://record/{model_name}/{record_id} resource"""
        from odoo_mcp.server import get_record

        mock_xmlrpc_server["models"].execute_kw.return_value = [sample_partner_records[0]]

        result = get_record("res.partner", "1")
        data = json.loads(result)

        assert data["id"] == 1
        assert data["name"] == "Test Company"

    def test_get_record_not_found(self, mock_env_config, mock_xmlrpc_server):
        """Test get_record with non-existent record"""
        from odoo_mcp.server import get_record

        mock_xmlrpc_server["models"].execute_kw.return_value = []

        result = get_record("res.partner", "99999")
        data = json.loads(result)

        assert "error" in data
        assert "not found" in data["error"]

    def test_get_record_invalid_id(self, mock_env_config, mock_xmlrpc_server):
        """Test get_record with invalid record ID"""
        from odoo_mcp.server import get_record

        result = get_record("res.partner", "invalid")
        data = json.loads(result)

        assert "error" in data

    def test_search_records_resource(self, mock_env_config, mock_xmlrpc_server, sample_partner_records):
        """Test the odoo://search/{model_name}/{domain} resource"""
        from odoo_mcp.server import search_records_resource

        mock_xmlrpc_server["models"].execute_kw.return_value = sample_partner_records

        domain = json.dumps([["is_company", "=", True]])
        result = search_records_resource("res.partner", domain)
        data = json.loads(result)

        assert len(data) == 3
        assert data[0]["name"] == "Test Company"

    def test_search_records_invalid_domain(self, mock_env_config, mock_xmlrpc_server):
        """Test search_records with invalid domain JSON"""
        from odoo_mcp.server import search_records_resource

        result = search_records_resource("res.partner", "invalid json")
        data = json.loads(result)

        assert "error" in data


class TestMCPTools:
    """Tests for MCP tool implementations"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_execute_method_success(self, mock_context):
        """Test execute_method tool with successful execution"""
        from odoo_mcp.server import execute_method

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = [1, 2, 3]

        result = execute_method(
            mock_context,
            model="res.partner",
            method="search",
            args=[[["is_company", "=", True]]],
        )

        assert result["success"] is True
        assert result["result"] == [1, 2, 3]

    def test_execute_method_failure(self, mock_context):
        """Test execute_method tool with execution failure"""
        from odoo_mcp.server import execute_method

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = Exception(
            "Access denied"
        )

        result = execute_method(
            mock_context,
            model="res.partner",
            method="unlink",
            args=[[1]],
        )

        assert result["success"] is False
        assert "Access denied" in result["error"]

    def test_execute_method_search_domain_normalization(self, mock_context):
        """Test domain normalization in execute_method for search"""
        from odoo_mcp.server import execute_method

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = [1]

        # Test with dict domain format
        result = execute_method(
            mock_context,
            model="res.partner",
            method="search",
            args=[{"conditions": [{"field": "name", "operator": "=", "value": "Test"}]}],
        )

        assert result["success"] is True

    def test_execute_method_with_kwargs(self, mock_context):
        """Test execute_method with keyword arguments"""
        from odoo_mcp.server import execute_method

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = []

        result = execute_method(
            mock_context,
            model="res.partner",
            method="search_read",
            args=[[]],
            kwargs={"fields": ["name"], "limit": 10},
        )

        assert result["success"] is True

    def test_search_employee_success(self, mock_context, sample_employee_data):
        """Test search_employee tool with successful search"""
        from odoo_mcp.server import search_employee

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = (
            sample_employee_data
        )

        result = search_employee(mock_context, name="John", limit=20)

        assert result.success is True
        assert len(result.result) == 3
        assert result.result[0].name == "John Doe"

    def test_search_employee_empty_result(self, mock_context):
        """Test search_employee with no matches"""
        from odoo_mcp.server import search_employee

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = []

        result = search_employee(mock_context, name="NonexistentName")

        assert result.success is True
        assert len(result.result) == 0

    def test_search_employee_error(self, mock_context):
        """Test search_employee with API error"""
        from odoo_mcp.server import search_employee

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = Exception(
            "HR module not installed"
        )

        result = search_employee(mock_context, name="John")

        assert result.success is False
        assert "HR module not installed" in result.error

    def test_search_holidays_success(self, mock_context, sample_holidays_data):
        """Test search_holidays tool with successful search"""
        from odoo_mcp.server import search_holidays

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = (
            sample_holidays_data
        )

        result = search_holidays(
            mock_context,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result.success is True
        assert len(result.result) == 2
        assert result.result[0].display_name == "Vacation - John Doe"

    def test_search_holidays_with_employee_id(self, mock_context, sample_holidays_data):
        """Test search_holidays with employee filter"""
        from odoo_mcp.server import search_holidays

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = [
            sample_holidays_data[0]
        ]

        result = search_holidays(
            mock_context,
            start_date="2024-01-01",
            end_date="2024-01-31",
            employee_id=1,
        )

        assert result.success is True
        assert len(result.result) == 1

    def test_search_holidays_invalid_start_date(self, mock_context):
        """Test search_holidays with invalid start date format"""
        from odoo_mcp.server import search_holidays

        result = search_holidays(
            mock_context,
            start_date="invalid-date",
            end_date="2024-01-31",
        )

        assert result.success is False
        assert "Invalid start_date format" in result.error

    def test_search_holidays_invalid_end_date(self, mock_context):
        """Test search_holidays with invalid end date format"""
        from odoo_mcp.server import search_holidays

        result = search_holidays(
            mock_context,
            start_date="2024-01-01",
            end_date="31-01-2024",
        )

        assert result.success is False
        assert "Invalid end_date format" in result.error

    def test_search_holidays_error(self, mock_context):
        """Test search_holidays with API error - returns empty results since search_read catches exceptions"""
        from odoo_mcp.server import search_holidays

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = Exception(
            "Table not found"
        )

        result = search_holidays(
            mock_context,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # Note: search_read catches exceptions and returns empty list,
        # so search_holidays returns success with empty results
        assert result.success is True
        assert result.result == []


class TestCRUDTools:
    """Tests for CRUD operation tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_create_record_success(self, mock_context):
        """Test create_record tool with successful creation"""
        from odoo_mcp.server import create_record

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = 42

        result = create_record(
            mock_context,
            model="res.partner",
            values={"name": "Test Partner", "email": "test@example.com"},
        )

        assert result["success"] is True
        assert result["id"] == 42
        assert result["model"] == "res.partner"

    def test_create_record_failure(self, mock_context):
        """Test create_record tool with failure"""
        from odoo_mcp.server import create_record

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = Exception(
            "Validation error"
        )

        result = create_record(
            mock_context,
            model="res.partner",
            values={"name": ""},
        )

        assert result["success"] is False
        assert "Validation error" in result["error"]

    def test_update_record_success(self, mock_context):
        """Test update_record tool with successful update"""
        from odoo_mcp.server import update_record

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = True

        result = update_record(
            mock_context,
            model="res.partner",
            ids=[1, 2],
            values={"phone": "123456789"},
        )

        assert result["success"] is True
        assert result["updated_ids"] == [1, 2]

    def test_delete_record_success(self, mock_context):
        """Test delete_record tool with successful deletion"""
        from odoo_mcp.server import delete_record

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = True

        result = delete_record(
            mock_context,
            model="res.partner",
            ids=[5, 6],
        )

        assert result["success"] is True
        assert result["deleted_ids"] == [5, 6]


class TestSearchTools:
    """Tests for search operation tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_search_records_success(self, mock_context, sample_partner_records):
        """Test search_records tool with successful search"""
        from odoo_mcp.server import search_records

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = [
            100,  # search_count
            sample_partner_records,  # search_read
        ]

        result = search_records(
            mock_context,
            model="res.partner",
            domain=[["is_company", "=", True]],
            limit=10,
        )

        assert result["success"] is True
        assert len(result["records"]) == 3
        assert result["count"] == 100
        assert result["has_more"] is True

    def test_search_records_pagination(self, mock_context):
        """Test search_records with pagination"""
        from odoo_mcp.server import search_records

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = [
            50,  # search_count
            [{"id": 21, "name": "Record 21"}],  # search_read
        ]

        result = search_records(
            mock_context,
            model="res.partner",
            domain=[],
            offset=20,
            limit=10,
        )

        assert result["success"] is True
        assert result["offset"] == 20
        assert result["limit"] == 10

    def test_count_records_success(self, mock_context):
        """Test count_records tool"""
        from odoo_mcp.server import count_records

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = 42

        result = count_records(
            mock_context,
            model="res.partner",
            domain=[["is_company", "=", True]],
        )

        assert result["success"] is True
        assert result["count"] == 42

    def test_read_records_tool_success(self, mock_context, sample_partner_records):
        """Test read_records tool"""
        from odoo_mcp.server import read_records as read_records_tool

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = sample_partner_records

        result = read_records_tool(
            mock_context,
            model="res.partner",
            ids=[1, 2, 3],
            fields=["name", "email"],
        )

        assert result["success"] is True
        assert len(result["records"]) == 3


class TestIntrospectionTools:
    """Tests for model introspection tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_get_fields_success(self, mock_context, sample_fields_data):
        """Test get_fields tool"""
        from odoo_mcp.server import get_fields

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = sample_fields_data

        result = get_fields(
            mock_context,
            model="res.partner",
        )

        assert result["success"] is True
        assert "fields" in result
        assert "name" in result["required_fields"]
        assert "partner_id" in result["relational_fields"]

    def test_get_default_values_success(self, mock_context):
        """Test get_default_values tool"""
        from odoo_mcp.server import get_default_values

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = {
            "active": True,
            "is_company": False,
        }

        result = get_default_values(
            mock_context,
            model="res.partner",
        )

        assert result["success"] is True
        assert result["defaults"]["active"] is True


class TestWorkflowTools:
    """Tests for workflow action tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_execute_action_success(self, mock_context):
        """Test execute_action tool"""
        from odoo_mcp.server import execute_action

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = True

        result = execute_action(
            mock_context,
            model="sale.order",
            ids=[1],
            action="action_confirm",
        )

        assert result["success"] is True
        assert result["action"] == "action_confirm"
        assert result["ids"] == [1]


class TestAttachmentTools:
    """Tests for attachment tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_list_attachments_success(self, mock_context):
        """Test list_attachments tool"""
        from odoo_mcp.server import list_attachments

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = [
            {"id": 1, "name": "document.pdf", "mimetype": "application/pdf"},
            {"id": 2, "name": "image.png", "mimetype": "image/png"},
        ]

        result = list_attachments(
            mock_context,
            model="res.partner",
            res_id=1,
        )

        assert result["success"] is True
        assert len(result["attachments"]) == 2
        assert result["count"] == 2

    def test_create_attachment_success(self, mock_context):
        """Test create_attachment tool"""
        from odoo_mcp.server import create_attachment

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = 10

        result = create_attachment(
            mock_context,
            name="test.pdf",
            model="res.partner",
            res_id=1,
            data="SGVsbG8gV29ybGQ=",  # base64 "Hello World"
            mimetype="application/pdf",
        )

        assert result["success"] is True
        assert result["attachment_id"] == 10


class TestCommonModelTools:
    """Tests for common model search tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_search_partners_success(self, mock_context, sample_partner_records):
        """Test search_partners tool"""
        from odoo_mcp.server import search_partners

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = [
            3,  # search_count
            sample_partner_records,  # search_read
        ]

        result = search_partners(
            mock_context,
            name="Test",
            is_company=True,
        )

        assert result["success"] is True
        assert len(result["partners"]) == 3
        assert result["count"] == 3

    def test_search_products_success(self, mock_context):
        """Test search_products tool"""
        from odoo_mcp.server import search_products

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = [
            2,  # search_count
            [
                {"id": 1, "name": "Laptop", "list_price": 999.99},
                {"id": 2, "name": "Mouse", "list_price": 29.99},
            ],
        ]

        result = search_products(
            mock_context,
            name="Laptop",
            sale_ok=True,
        )

        assert result["success"] is True
        assert len(result["products"]) == 2

    def test_search_sale_orders_success(self, mock_context):
        """Test search_sale_orders tool"""
        from odoo_mcp.server import search_sale_orders

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = [
            1,  # search_count
            [{"id": 1, "name": "SO001", "state": "sale", "amount_total": 1500.00}],
        ]

        result = search_sale_orders(
            mock_context,
            state="sale",
        )

        assert result["success"] is True
        assert len(result["orders"]) == 1
        assert result["orders"][0]["name"] == "SO001"

    def test_search_invoices_success(self, mock_context):
        """Test search_invoices tool"""
        from odoo_mcp.server import search_invoices

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.side_effect = [
            1,  # search_count
            [{"id": 1, "name": "INV/2024/0001", "state": "posted", "amount_total": 1000.00}],
        ]

        result = search_invoices(
            mock_context,
            state="posted",
            move_type="out_invoice",
        )

        assert result["success"] is True
        assert len(result["invoices"]) == 1


class TestMessagingTools:
    """Tests for messaging/chatter tools"""

    @pytest.fixture
    def mock_context(self, mock_odoo_client):
        """Create a mock MCP context with Odoo client"""
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.lifespan_context = Mock()
        ctx.request_context.lifespan_context.odoo = mock_odoo_client
        return ctx

    def test_post_message_success(self, mock_context):
        """Test post_message tool"""
        from odoo_mcp.server import post_message

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = 123

        result = post_message(
            mock_context,
            model="sale.order",
            res_id=1,
            body="<p>Test message</p>",
        )

        assert result["success"] is True
        assert result["message_id"] == 123

    def test_get_messages_success(self, mock_context):
        """Test get_messages tool"""
        from odoo_mcp.server import get_messages

        mock_context.request_context.lifespan_context.odoo._models.execute_kw.return_value = [
            {"id": 1, "body": "Message 1", "date": "2024-01-15 10:00:00"},
            {"id": 2, "body": "Message 2", "date": "2024-01-14 09:00:00"},
        ]

        result = get_messages(
            mock_context,
            model="sale.order",
            res_id=1,
        )

        assert result["success"] is True
        assert len(result["messages"]) == 2


class TestPydanticModels:
    """Tests for Pydantic model definitions"""

    def test_domain_condition(self):
        """Test DomainCondition model"""
        from odoo_mcp.server import DomainCondition

        condition = DomainCondition(
            field="name",
            operator="=",
            value="Test",
        )

        assert condition.to_tuple() == ["name", "=", "Test"]

    def test_search_domain(self):
        """Test SearchDomain model"""
        from odoo_mcp.server import SearchDomain, DomainCondition

        domain = SearchDomain(
            conditions=[
                DomainCondition(field="name", operator="ilike", value="test"),
                DomainCondition(field="is_company", operator="=", value=True),
            ]
        )

        domain_list = domain.to_domain_list()

        assert len(domain_list) == 2
        assert domain_list[0] == ["name", "ilike", "test"]
        assert domain_list[1] == ["is_company", "=", True]

    def test_employee_search_result(self):
        """Test EmployeeSearchResult model"""
        from odoo_mcp.server import EmployeeSearchResult

        employee = EmployeeSearchResult(id=1, name="John Doe")

        assert employee.id == 1
        assert employee.name == "John Doe"

    def test_search_employee_response_success(self):
        """Test SearchEmployeeResponse success model"""
        from odoo_mcp.server import SearchEmployeeResponse, EmployeeSearchResult

        response = SearchEmployeeResponse(
            success=True,
            result=[
                EmployeeSearchResult(id=1, name="John Doe"),
            ],
        )

        assert response.success is True
        assert len(response.result) == 1

    def test_search_employee_response_error(self):
        """Test SearchEmployeeResponse error model"""
        from odoo_mcp.server import SearchEmployeeResponse

        response = SearchEmployeeResponse(
            success=False,
            error="API error occurred",
        )

        assert response.success is False
        assert response.error == "API error occurred"
        assert response.result is None

    def test_holiday_model(self):
        """Test Holiday model"""
        from odoo_mcp.server import Holiday

        holiday = Holiday(
            display_name="Vacation",
            start_datetime="2024-01-15 08:00:00",
            stop_datetime="2024-01-19 17:00:00",
            employee_id=[1, "John Doe"],
            name="Annual Leave",
            state="validate",
        )

        assert holiday.display_name == "Vacation"
        assert holiday.state == "validate"

    def test_search_holidays_response(self):
        """Test SearchHolidaysResponse model"""
        from odoo_mcp.server import SearchHolidaysResponse, Holiday

        response = SearchHolidaysResponse(
            success=True,
            result=[
                Holiday(
                    display_name="Vacation",
                    start_datetime="2024-01-15 08:00:00",
                    stop_datetime="2024-01-19 17:00:00",
                    employee_id=[1, "John Doe"],
                    name="Annual Leave",
                    state="validate",
                ),
            ],
        )

        assert response.success is True
        assert len(response.result) == 1


class TestAppLifespan:
    """Tests for application lifespan management"""

    @pytest.mark.asyncio
    async def test_app_lifespan(self, mock_env_config, mock_xmlrpc_server):
        """Test app lifespan context manager"""
        from odoo_mcp.server import app_lifespan, mcp

        async with app_lifespan(mcp) as ctx:
            assert ctx.odoo is not None
            assert ctx.odoo.uid == 1


class TestAppContext:
    """Tests for AppContext dataclass"""

    def test_app_context(self, mock_odoo_client):
        """Test AppContext creation"""
        from odoo_mcp.server import AppContext

        ctx = AppContext(odoo=mock_odoo_client)

        assert ctx.odoo is mock_odoo_client
