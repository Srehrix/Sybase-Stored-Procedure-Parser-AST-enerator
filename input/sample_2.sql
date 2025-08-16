CREATE PROCEDURE [dbo].[sp_manage_employee_tasks]
    @emp_id INT
AS
BEGIN
    DECLARE @task_count INT
    DECLARE @i INT
    DECLARE @message VARCHAR(200)

    -- Initialize counters
    SET @task_count = (SELECT COUNT(*) FROM Tasks WHERE EmployeeID = @emp_id)
    SET @i = 1

    IF @task_count > 0
    BEGIN
        SET @message = 'Tasks found for employee.'

        WHILE @i <= @task_count
        BEGIN
            DECLARE @task_id INT
            SELECT @task_id = TaskID 
            FROM (
                SELECT TaskID, ROW_NUMBER() OVER (ORDER BY TaskID) AS rn
                FROM Tasks
                WHERE EmployeeID = @emp_id
            ) AS T
            WHERE rn = @i

            -- Nested IF inside WHILE
            IF EXISTS (SELECT 1 FROM Tasks WHERE TaskID = @task_id AND Status = 'Pending')
            BEGIN
                UPDATE Tasks
                SET Status = 'InProgress'
                WHERE TaskID = @task_id
            END
            ELSE
            BEGIN
                SET @message = 'No pending tasks.'
            END

            SET @i = @i + 1
        END
    END
    ELSE
    BEGIN
        SET @message = 'No tasks assigned.'
    END

    SELECT @message AS StatusMessage

    RETURN
END
