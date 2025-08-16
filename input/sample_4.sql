CREATE PROCEDURE [dbo].[sp_full_feature_test]
    @emp_id INT
AS
BEGIN
    DECLARE @task_count INT
    DECLARE @i INT
    DECLARE @message VARCHAR(200)
    DECLARE @task_id INT

    SET @task_count = (SELECT COUNT(*) FROM Tasks WHERE EmployeeID = @emp_id)
    SET @i = 1

    IF @task_count > 0
    BEGIN
        SET @message = 'Tasks found.'
        WHILE @i <= @task_count
        BEGIN
            SELECT @task_id = TaskID
            FROM (
                SELECT TaskID, ROW_NUMBER() OVER (ORDER BY TaskID) AS rn
                FROM Tasks
                WHERE EmployeeID = @emp_id
            ) AS T
            WHERE rn = @i

            IF EXISTS (SELECT 1 FROM Tasks WHERE TaskID = @task_id AND Status = 'Pending')
            BEGIN
                SET @message = 'Processing pending task.'
                UPDATE Tasks SET Status = 'In Progress' WHERE TaskID = @task_id
            END
            ELSE
            BEGIN
                DELETE FROM Tasks WHERE TaskID = @task_id AND Status = 'Completed'
            END

            SET @i = @i + 1
        END
    END
    ELSE
    BEGIN
        SET @message = 'No tasks found. Creating default task.'
        INSERT INTO Tasks (EmployeeID, TaskName, Status) VALUES (@emp_id, 'Default Task', 'Pending')
    END

    EXEC sp_log_message @message
    SELECT @message AS FinalMessage
    RETURN
END
