from workflows.nodes import Node00Input
from workflows.models import WorkflowContext, NodeOutput, Issue
from datetime import datetime

def main():
    filepath = r'/Users/cb/Desktop/byd/workflow/table/1-链接.xlsx'
    context = WorkflowContext(
        run_id='1',
        run_started_at=datetime.now(),
        input_file=filepath,
        table_dir='./table'
    )
    node1 = Node00Input()
    res = node1.process(context)
    print(res)

if __name__ == "__main__":
    main()