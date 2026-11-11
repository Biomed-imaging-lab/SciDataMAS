from typing import List, Dict
from pydantic import BaseModel, Field


class DAGNode(BaseModel):
    node_id: str = Field(description="Unique snake_case identifier for this node")
    name: str = Field(description="Human-readable name, 3-6 words")
    description: str = Field(
        description="One sentence: what this node represents in the experiment"
    )


class DAGEdge(BaseModel):
    source: str = Field(description="node_id of the source node")
    target: str = Field(description="node_id of the target node")


class DAG(BaseModel):
    nodes: Dict[str, DAGNode] = Field(description="All nodes in the DAG")
    edges: List[DAGEdge] = Field(description="All directed edges in the DAG")


def convert_to_DAG(nodes: List[DAGNode], edges: List[DAGEdge]) -> DAG:
    node_dict = {n.node_id: n for n in nodes}
    dag = DAG(nodes=node_dict, edges=edges)
    return dag


class Validator:
    def __init__(self):
        return

    def __indexes_check(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        issues = []

        nodes_set = set()
        for node in nodes:
            if node.node_id in nodes_set:
                issues.append(
                    f'[Node\'s id collision]: id "{node.node_id}" used multiple times (repeared in {node.name} node).'
                )
            else:
                nodes_set.add(node.node_id)

        for edge in edges:
            if edge.source not in nodes_set:
                issues.append(
                    f'[Edges\'s bad id]: some edge have unknown node id as a source - "{edge.source}".'
                )
            if edge.target not in nodes_set:
                issues.append(
                    f'[Edges\'s bad id]: some edge have unknown node id as a target - "{edge.target}".'
                )
        return issues

    def __check_linkage(self, edges: List[DAGEdge]):
        issues = []

        if len(self.node_ids) <= 1:
            return True

        # Build undirected adjacency
        adj = {n: set() for n in self.node_ids}
        for e in edges:
            if e.source in adj and e.target in adj:
                adj[e.source].add(e.target)
                adj[e.target].add(e.source)

        # BFS from any node
        start = next(iter(self.node_ids))
        visited = {start}
        queue = [start]
        while queue:
            node = queue.pop()
            for nb in adj[node]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)

        if visited != self.node_ids:
            visited_str = ", ".join([f'"{v}"' for v in visited])
            unvisited = self.node_ids - visited
            unvisited_str = ", ".join([f'"{uv}"' for uv in unvisited])
            issues = [
                f"[Not Single linkage DAG graph] - Some nodes are not linkaged to another: list one ({visited_str}) and list two ({unvisited_str}) are disconnected."
            ]
        return issues

    def __loops_check(self):
        visited = set()
        rec_stack = set()
        issues = []

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for nb in self.out_edges.get(node, []):
                if nb not in visited:
                    if has_cycle(nb):
                        return True
                elif nb in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for nid in self.node_ids:
            if nid not in visited:
                if has_cycle(nid):
                    issues.append(
                        "[Cycled DAG] Graph contains a cycle - DAG must be acyclic"
                    )
                    break
        return issues

    def __call__(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        self.node_dict = {n.node_id: n for n in nodes}
        self.node_ids = set(self.node_dict)
        self.in_edges = {n: [] for n in self.node_ids}
        self.out_edges = {n: [] for n in self.node_ids}

        total_issues = []

        # 1st - id checking
        # - check dublicates in nodes ids
        # - check that edges have correct nodes' ids in them
        total_issues += self.__indexes_check(nodes, edges)

        # 2nd - checking on loops
        total_issues += self.__loops_check()

        # 3rd - checking on undirected single linkage of graphs nodes
        total_issues += self.__check_linkage(edges)

        return total_issues
