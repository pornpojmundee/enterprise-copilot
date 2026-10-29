"""The semantic layer as the LLM sees it: views, columns, meanings and allowed values.
Kept in code (not introspected) so descriptions are curated and nothing sensitive leaks in."""

SCHEMA_DOC = """\
All views are in schema copilot_data. Row-level security already limits rows to what the asking user may see.

employees(employee_id 'NT0001', first_name_th, last_name_th, first_name_en, last_name_en, nickname, email,
          dept_id, team_id, position, level 'L1'..'L6', manager_id, location 'Bangkok HQ'|'Chiang Mai Office',
          hire_date, employment_status 'active'|'probation'|'resigned')
teams(team_id e.g. 'DATA-DE', name_en, name_th, dept_id, lead_employee_id)
departments(dept_id 'EXE'|'ENG'|'DATA'|'SALES'|'HR'|'FIN'|'IT', name_en, name_th, head_employee_id)
holidays(holiday_date, name_th, name_en, is_substitute)            -- company holidays
leave_balances(employee_id, year, leave_type 'VAC'|'SICK'|'PER', entitled, carried_over, used, pending, remaining)
    -- VAC = ลาพักร้อน, SICK = ลาป่วย, PER = ลากิจ; values are working days
leave_requests(request_id, employee_id, leave_type, start_date, end_date, half_day 'am'|'pm'|NULL,
               working_days, status 'pending'|'approved'|'rejected'|'cancelled', reason, created_at)
tickets(ticket_id 'IT-0001'|'HR-0001' (format), category 'it'|'hr', subcategory, title, description,
        requester_id, requester_team_id, assigned_team_id, assignee_id,
        priority 'P1'..'P4', status 'open'|'in_progress'|'waiting'|'resolved'|'closed',
        created_at, first_response_at, resolved_at, sla_due_at, resolution,
        is_open boolean, sla_breached boolean)
    -- subcategory: hardware-notebook, hardware-peripheral, account-password, network-vpn, email-outlook,
    --   software-request, access-request, security-phishing, payroll, leave-correction, document-request, benefits
ticket_comments(comment_id, ticket_id, author_id, body, created_at)
sla_policies(priority, description, response_hours, resolve_hours)
"""
