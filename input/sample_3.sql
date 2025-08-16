CREATE PROCEDURE [dbo].[sp_manage_employee_tasks]
    @emp_id INT
AS
BEGIN
    DECLARE @task_count INT
    DECLARE @i INT
    DECLARE @message VARCHAR(200)
    DECLARE @task_id INT

    SET @task_count = (SELECT COUNT(*) FROM Tasks WHERE EmployeeID = @emp_id)
    SELECT COUNT(*) FROM Tasks WHERE EmployeeID = @emp_id

    SET @i = 1

    IF @task_count > 0
    BEGIN
        SET @message = 'Tasks found for employee.'

        WHILE @i <= @task_count
        BEGIN
            SELECT @task_id = TaskID 
            FROM (
                SELECT TaskID, ROW_NUMBER() OVER (ORDER BY TaskID) AS rn 
                FROM Tasks 
                WHERE EmployeeID = @emp_id
            ) AS T
            WHERE rn = @i

            SELECT TaskID, ROW_NUMBER() OVER (ORDER BY TaskID) AS rn 
            FROM Tasks 
            WHERE EmployeeID = @emp_id

            IF EXISTS (SELECT 1 FROM Tasks WHERE TaskID = @task_id AND Status = 'Pending')
            BEGIN
                SELECT 1 FROM Tasks WHERE TaskID = @task_id AND Status = 'Pending'
                SET @message = 'Task is still pending.'
            END
            ELSE
            BEGIN
                UPDATE Tasks SET Status = 'Completed' WHERE TaskID = @task_id
                SET @message = 'Task was marked completed.'
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
