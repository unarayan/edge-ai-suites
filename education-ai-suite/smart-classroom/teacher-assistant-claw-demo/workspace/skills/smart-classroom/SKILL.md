# Skill: Smart Classroom Report Generator

## Description

This skill enables the Teacher Assistant agent to interact with the Smart Classroom application API to fetch classroom analytics data and generate structured reports.

## Triggers

- User requests a report (class-level, grade-level, or school-level)
- User asks about classroom statistics or engagement metrics

## Data Source

Classroom data files are located in `~/smart_classroom_incoming`. The agent reads reports and analytics from this directory.

## Inputs

- Classroom ID or grade identifier
- Report type (attendance, engagement, performance)
- Time range (daily, weekly, monthly)

## Steps

1. Read data files from `~/smart_classroom_incoming`
2. Identify relevant data for the requested scope (class, grade, or school)
3. Process and aggregate data as needed
4. Format the report in the requested style
5. Present results to the user

## Configuration

- **Data Directory**: `~/smart_classroom_incoming`
- **Data Format**: Files deposited by the Smart Classroom application

## Example Usage

```
User: Generate a weekly engagement report for Grade 3
Assistant: Fetching data for all Grade 3 classrooms...
```

