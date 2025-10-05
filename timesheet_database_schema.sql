
-- Database Schema for Conversational Timesheet Chatbot

-- Oracle Timesheet Table
CREATE TABLE OracleTimesheet (
    ID BIGINT IDENTITY(1,1) PRIMARY KEY,
    UserEmail NVARCHAR(255) NOT NULL,
    EntryDate DATE NOT NULL,
    ProjectCode NVARCHAR(50) NOT NULL,
    TaskCode NVARCHAR(50),
    Hours DECIMAL(5,2) NOT NULL CHECK (Hours > 0 AND Hours <= 24),
    Description NVARCHAR(500),
    Status NVARCHAR(20) DEFAULT 'Draft' CHECK (Status IN ('Draft', 'Submitted', 'Approved')),
    CreatedAt DATETIME2 DEFAULT GETDATE(),
    UpdatedAt DATETIME2 DEFAULT GETDATE(),

    INDEX IX_OracleTimesheet_UserEmail_Date (UserEmail, EntryDate),
    INDEX IX_OracleTimesheet_ProjectCode (ProjectCode),
    INDEX IX_OracleTimesheet_Status (Status)
);

-- Mars Timesheet Table
CREATE TABLE MarsTimesheet (
    ID BIGINT IDENTITY(1,1) PRIMARY KEY,
    UserEmail NVARCHAR(255) NOT NULL,
    EntryDate DATE NOT NULL,
    ProjectCode NVARCHAR(50) NOT NULL,
    TaskCode NVARCHAR(50),
    Hours DECIMAL(5,2) NOT NULL CHECK (Hours > 0 AND Hours <= 24),
    Description NVARCHAR(500),
    Status NVARCHAR(20) DEFAULT 'Draft' CHECK (Status IN ('Draft', 'Submitted', 'Approved')),
    CreatedAt DATETIME2 DEFAULT GETDATE(),
    UpdatedAt DATETIME2 DEFAULT GETDATE(),

    INDEX IX_MarsTimesheet_UserEmail_Date (UserEmail, EntryDate),
    INDEX IX_MarsTimesheet_ProjectCode (ProjectCode),
    INDEX IX_MarsTimesheet_Status (Status)
);

-- User Sessions for conversation context
CREATE TABLE UserSessions (
    SessionID UNIQUEIDENTIFIER DEFAULT NEWID() PRIMARY KEY,
    UserEmail NVARCHAR(255) NOT NULL,
    ConversationContext NVARCHAR(MAX),
    SelectedSystem NVARCHAR(20) CHECK (SelectedSystem IN ('Oracle', 'Mars')),
    LastActivity DATETIME2 DEFAULT GETDATE(),
    CreatedAt DATETIME2 DEFAULT GETDATE(),

    INDEX IX_UserSessions_UserEmail (UserEmail),
    INDEX IX_UserSessions_LastActivity (LastActivity)
);

-- Project Codes reference table
CREATE TABLE ProjectCodes (
    ID INT IDENTITY(1,1) PRIMARY KEY,
    ProjectCode NVARCHAR(50) UNIQUE NOT NULL,
    ProjectName NVARCHAR(200) NOT NULL,
    IsActive BIT DEFAULT 1,
    System NVARCHAR(20) NOT NULL CHECK (System IN ('Oracle', 'Mars', 'Both'))
);

-- Insert sample project codes
INSERT INTO ProjectCodes (ProjectCode, ProjectName, System) VALUES
('ORG-001', 'Oracle General Development', 'Oracle'),
('ORG-002', 'Oracle Database Maintenance', 'Oracle'),
('ORG-003', 'Oracle Integration Project', 'Oracle'),
('MRS-001', 'Mars Platform Development', 'Mars'),
('MRS-002', 'Mars Analytics Module', 'Mars'),
('MRS-003', 'Mars Security Enhancement', 'Mars'),
('CMN-001', 'Common Infrastructure', 'Both'),
('CMN-002', 'Documentation and Training', 'Both');
