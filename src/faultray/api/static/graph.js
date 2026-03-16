/* =========================================================
   FaultRay - D3.js Force-Directed Dependency Graph
   ========================================================= */

(function () {
    "use strict";

    const TYPE_COLORS = {
        load_balancer: "#e94560",
        app_server: "#6c5ce7",
        web_server: "#6c5ce7",
        database: "#00b894",
        cache: "#fdcb6e",
        queue: "#0984e3",
        storage: "#a0a0a0",
        dns: "#a0a0a0",
        external_api: "#a0a0a0",
        custom: "#a0a0a0",
    };

    const HEALTH_COLORS = {
        healthy: "#00b894",
        degraded: "#f0a500",
        overloaded: "#fdcb6e",
        down: "#e94560",
    };

    const container = document.getElementById("graphCanvas");
    if (!container) return;

    const tooltip = document.getElementById("nodeTooltip");

    const width = container.clientWidth;
    const height = container.clientHeight;

    const svg = d3
        .select(container)
        .append("svg")
        .attr("width", width)
        .attr("height", height);

    // Zoom layer
    const g = svg.append("g");

    const zoom = d3
        .zoom()
        .scaleExtent([0.2, 4])
        .on("zoom", (event) => {
            g.attr("transform", event.transform);
        });

    svg.call(zoom);

    // Expose zoom and svg globally for external controls
    window._graphZoom = zoom;
    window._graphSvg = svg;

    // Arrow marker definitions
    svg.append("defs")
        .selectAll("marker")
        .data(["requires", "optional", "async"])
        .enter()
        .append("marker")
        .attr("id", (d) => "arrow-" + d)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 20)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "#4a5568");

    // Fetch data and render
    fetch("/api/graph-data")
        .then((r) => r.json())
        .then((data) => {
            if (!data.nodes || data.nodes.length === 0) return;
            render(data);
        })
        .catch((err) => {
            console.error("Failed to load graph data:", err);
        });

    function render(data) {
        const nodes = data.nodes;
        const edges = data.edges;

        // Compute node sizes based on dependents count
        const maxDep = Math.max(1, ...nodes.map((n) => n.dependents_count));

        const simulation = d3
            .forceSimulation(nodes)
            .force(
                "link",
                d3
                    .forceLink(edges)
                    .id((d) => d.id)
                    .distance(140)
            )
            .force("charge", d3.forceManyBody().strength(-400))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(40));

        // Draw edges
        const link = g
            .selectAll(".link")
            .data(edges)
            .enter()
            .append("line")
            .attr("class", "link")
            .attr("stroke", "#4a5568")
            .attr("stroke-width", 1.5)
            .attr("marker-end", (d) => "url(#arrow-" + d.dependency_type + ")")
            .attr("stroke-dasharray", (d) => {
                if (d.dependency_type === "optional") return "8,4";
                if (d.dependency_type === "async") return "3,3";
                return null;
            })
            .attr("stroke-opacity", 0.7);

        // Draw edge labels
        const linkLabel = g
            .selectAll(".link-label")
            .data(edges)
            .enter()
            .append("text")
            .attr("class", "link-label")
            .attr("font-size", 9)
            .attr("fill", "#4a5568")
            .attr("text-anchor", "middle")
            .text((d) => d.dependency_type);

        // Draw nodes
        const node = g
            .selectAll(".node")
            .data(nodes)
            .enter()
            .append("g")
            .attr("class", "node")
            .call(
                d3
                    .drag()
                    .on("start", dragStarted)
                    .on("drag", dragged)
                    .on("end", dragEnded)
            );

        // Node circle
        node.append("circle")
            .attr("r", (d) => 14 + (d.dependents_count / maxDep) * 12)
            .attr("fill", (d) => TYPE_COLORS[d.type] || "#a0a0a0")
            .attr("stroke", (d) => HEALTH_COLORS[d.health] || "#4a5568")
            .attr("stroke-width", 2.5)
            .attr("opacity", 0.9);

        // Node label
        node.append("text")
            .attr("dy", (d) => 14 + (d.dependents_count / maxDep) * 12 + 16)
            .attr("text-anchor", "middle")
            .attr("fill", "#a0aec0")
            .attr("font-size", 11)
            .attr("font-weight", 600)
            .text((d) => d.name);

        // Node icon letter
        node.append("text")
            .attr("dy", 5)
            .attr("text-anchor", "middle")
            .attr("fill", "#fff")
            .attr("font-size", 12)
            .attr("font-weight", 700)
            .text((d) => {
                const map = {
                    load_balancer: "LB",
                    app_server: "A",
                    web_server: "W",
                    database: "DB",
                    cache: "C",
                    queue: "Q",
                    storage: "S",
                    dns: "D",
                    external_api: "E",
                    custom: "?",
                };
                return map[d.type] || "?";
            });

        // Hover: tooltip
        node.on("mouseover", (event, d) => {
            tooltip.style.display = "block";
            tooltip.innerHTML = `
                <div class="tt-name">${d.name}</div>
                <div class="tt-row"><span class="tt-label">Type</span><span>${d.type.replace("_", " ")}</span></div>
                <div class="tt-row"><span class="tt-label">Host</span><span>${d.host}:${d.port}</span></div>
                <div class="tt-row"><span class="tt-label">Replicas</span><span>${d.replicas}</span></div>
                <div class="tt-row"><span class="tt-label">Health</span><span>${d.health}</span></div>
                <div class="tt-row"><span class="tt-label">Utilization</span><span>${d.utilization}%</span></div>
                <div class="tt-row"><span class="tt-label">CPU</span><span>${d.cpu_percent}%</span></div>
                <div class="tt-row"><span class="tt-label">Memory</span><span>${d.memory_percent}%</span></div>
                <div class="tt-row"><span class="tt-label">Dependents</span><span>${d.dependents_count}</span></div>
            `;
        })
            .on("mousemove", (event) => {
                tooltip.style.left = event.clientX + 14 + "px";
                tooltip.style.top = event.clientY - 10 + "px";
            })
            .on("mouseout", () => {
                tooltip.style.display = "none";
            });

        // Click: highlight cascade paths
        let highlighted = false;
        node.on("click", (event, d) => {
            event.stopPropagation();

            if (highlighted === d.id) {
                // Reset
                resetHighlight();
                highlighted = false;
                return;
            }

            highlighted = d.id;

            // Dim everything
            node.selectAll("circle").attr("opacity", 0.2);
            node.selectAll("text").attr("opacity", 0.2);
            link.attr("stroke-opacity", 0.08);
            linkLabel.attr("opacity", 0.08);

            // Collect connected node IDs
            const connected = new Set([d.id]);
            edges.forEach((e) => {
                const sid = typeof e.source === "object" ? e.source.id : e.source;
                const tid = typeof e.target === "object" ? e.target.id : e.target;
                if (sid === d.id) connected.add(tid);
                if (tid === d.id) connected.add(sid);
            });

            // Highlight connected
            node.filter((n) => connected.has(n.id))
                .selectAll("circle")
                .attr("opacity", 1);
            node.filter((n) => connected.has(n.id))
                .selectAll("text")
                .attr("opacity", 1);

            link.filter((l) => {
                const sid = typeof l.source === "object" ? l.source.id : l.source;
                const tid = typeof l.target === "object" ? l.target.id : l.target;
                return sid === d.id || tid === d.id;
            })
                .attr("stroke-opacity", 1)
                .attr("stroke", "#e94560")
                .attr("stroke-width", 2.5);

            linkLabel
                .filter((l) => {
                    const sid =
                        typeof l.source === "object" ? l.source.id : l.source;
                    const tid =
                        typeof l.target === "object" ? l.target.id : l.target;
                    return sid === d.id || tid === d.id;
                })
                .attr("opacity", 1);
        });

        // Click canvas to reset
        svg.on("click", () => {
            if (highlighted) {
                resetHighlight();
                highlighted = false;
            }
        });

        function resetHighlight() {
            node.selectAll("circle").attr("opacity", 0.9);
            node.selectAll("text").attr("opacity", 1);
            link.attr("stroke-opacity", 0.7)
                .attr("stroke", "#4a5568")
                .attr("stroke-width", 1.5);
            linkLabel.attr("opacity", 1);
        }

        // Simulation tick
        simulation.on("tick", () => {
            link.attr("x1", (d) => d.source.x)
                .attr("y1", (d) => d.source.y)
                .attr("x2", (d) => d.target.x)
                .attr("y2", (d) => d.target.y);

            linkLabel
                .attr("x", (d) => (d.source.x + d.target.x) / 2)
                .attr("y", (d) => (d.source.y + d.target.y) / 2 - 6);

            node.attr("transform", (d) => `translate(${d.x},${d.y})`);
        });

        // Drag handlers
        function dragStarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragEnded(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }
    }
})();
