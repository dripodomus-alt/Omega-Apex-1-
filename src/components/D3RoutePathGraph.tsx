import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { ArbitrageRoute } from '../types';
import { Dna, Zap, Layers, RefreshCw, Eye } from 'lucide-react';

interface D3RoutePathGraphProps {
  route: ArbitrageRoute | null;
  height?: number;
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  type: 'token' | 'pool';
  isOrigin?: boolean;
  step: number;
  targetX?: number;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
  label?: string;
}

export const D3RoutePathGraph: React.FC<D3RoutePathGraphProps> = ({
  route,
  height = 220,
}) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hoveredNode, setHoveredNode] = useState<{ label: string; type: string; step: number } | null>(null);

  useEffect(() => {
    if (!svgRef.current || !route) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove(); // Clear previous diagram

    const width = containerRef.current?.clientWidth || 700;

    // Parse path parts from route
    const rawParts = route.pathString.split(' -> ').map((s) => s.trim());

    // Build nodes and links
    const nodes: GraphNode[] = [];
    const links: GraphLink[] = [];

    const totalSteps = rawParts.length;
    const paddingX = 70;
    const availableWidth = width - paddingX * 2;

    rawParts.forEach((part, index) => {
      const isPool =
        part.includes('Uni') ||
        part.includes('Quick') ||
        part.includes('Sushi') ||
        part.includes('Curve') ||
        part.includes('Aave') ||
        part.includes('Balancer') ||
        part.includes('DEX') ||
        part.includes('v3') ||
        part.includes('v2');

      const isOrigin = index === 0 || index === totalSteps - 1;
      const stepFraction = totalSteps > 1 ? index / (totalSteps - 1) : 0.5;
      const targetX = paddingX + stepFraction * availableWidth;

      const nodeId = `node_${index}_${part.replace(/[^a-zA-Z0-9]/g, '_')}`;

      nodes.push({
        id: nodeId,
        label: part,
        type: isPool ? 'pool' : 'token',
        isOrigin,
        step: index + 1,
        targetX,
        x: targetX,
        y: height / 2 + (index % 2 === 0 ? -10 : 10),
      });

      if (index > 0) {
        links.push({
          source: nodes[index - 1].id,
          target: nodeId,
          label: `Hop ${index}`,
        });
      }
    });

    // Create SVG Defs for markers and filters
    const defs = svg.append('defs');

    // Arrowhead marker
    defs
      .append('marker')
      .attr('id', 'd3-arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#10b981');

    // Glow Filter
    const filter = defs.append('filter').attr('id', 'd3-glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%');
    filter.append('feGaussianBlur').attr('stdDeviation', '4').attr('result', 'coloredBlur');
    const feMerge = filter.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'coloredBlur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    // Simulation Setup
    const simulation = d3
      .forceSimulation<GraphNode>(nodes)
      .force('charge', d3.forceManyBody().strength(-150))
      .force('link', d3.forceLink<GraphNode, GraphLink>(links).id((d) => d.id).distance(80))
      .force(
        'x',
        d3.forceX<GraphNode>()
          .x((d) => d.targetX || width / 2)
          .strength(0.85)
      )
      .force(
        'y',
        d3.forceY<GraphNode>()
          .y(height / 2)
          .strength(0.7)
      )
      .force('collision', d3.forceCollide().radius(32));

    // Draw Links
    const linkGroup = svg.append('g').attr('class', 'links');
    const linkPaths = linkGroup
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', '#059669')
      .attr('stroke-width', 2.5)
      .attr('stroke-dasharray', '6, 3')
      .attr('marker-end', 'url(#d3-arrowhead)')
      .attr('opacity', 0.85);

    // Flow Animation on links
    let dashOffset = 0;
    const timer = d3.timer(() => {
      dashOffset -= 0.5;
      linkPaths.style('stroke-dashoffset', `${dashOffset}px`);
    });

    // Draw Nodes
    const nodeGroup = svg.append('g').attr('class', 'nodes');

    const nodeG = nodeGroup
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .attr('cursor', 'grab')
      .call(
        d3
          .drag<SVGGElement, GraphNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // Node Circles
    nodeG
      .append('circle')
      .attr('r', (d) => (d.type === 'pool' ? 18 : 22))
      .attr('fill', (d) =>
        d.isOrigin
          ? '#064e3b'
          : d.type === 'pool'
          ? '#3b0764'
          : '#022c22'
      )
      .attr('stroke', (d) =>
        d.isOrigin
          ? '#34d399'
          : d.type === 'pool'
          ? '#a855f7'
          : '#10b981'
      )
      .attr('stroke-width', (d) => (d.isOrigin ? 3 : 2))
      .attr('filter', 'url(#d3-glow)')
      .on('mouseover', (_event, d) => {
        setHoveredNode({ label: d.label, type: d.type, step: d.step });
      })
      .on('mouseout', () => {
        setHoveredNode(null);
      });

    // Inner Icons or Symbols
    nodeG
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', (d) => (d.type === 'pool' ? '#e9d5ff' : '#a7f3d0'))
      .attr('font-size', (d) => (d.type === 'pool' ? '10px' : '11px'))
      .attr('font-weight', 'bold')
      .attr('font-family', 'monospace')
      .attr('pointer-events', 'none')
      .text((d) => (d.type === 'pool' ? 'DEX' : d.label.split(' ')[0].slice(0, 5)));

    // Labels below nodes
    nodeG
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('y', 36)
      .attr('fill', '#94a3b8')
      .attr('font-size', '10px')
      .attr('font-family', 'monospace')
      .attr('font-weight', '600')
      .text((d) => (d.label.length > 18 ? d.label.slice(0, 16) + '..' : d.label));

    // Simulation Tick
    simulation.on('tick', () => {
      linkPaths
        .attr('x1', (d) => (d.source as GraphNode).x!)
        .attr('y1', (d) => (d.source as GraphNode).y!)
        .attr('x2', (d) => (d.target as GraphNode).x!)
        .attr('y2', (d) => (d.target as GraphNode).y!);

      nodeG.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
      timer.stop();
    };
  }, [route, height]);

  if (!route) {
    return (
      <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-6 text-center text-slate-500 font-mono text-xs flex flex-col items-center justify-center gap-2 h-[180px]">
        <Eye className="w-8 h-8 text-slate-700 animate-pulse" />
        <span className="text-slate-400 font-semibold">Hover over any Arbitrage Route below</span>
        <span>D3.js dynamic graph visualizes hop sequence, token paths & DEX liquidity nodes in real time.</span>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="bg-slate-950 border border-slate-800 rounded-xl p-4 shadow-2xl relative space-y-2 font-mono">
      {/* Visual Header Banner */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-emerald-950 border border-emerald-800 rounded-lg text-emerald-400">
            <Dna className="w-4 h-4 animate-spin-slow" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                D3.js Dynamic Route Hop Graph
              </span>
              <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-bold rounded">
                {route.id}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 truncate max-w-md">
              Path: {route.pathString}
            </div>
          </div>
        </div>

        {/* Hovered Node Info or Route Metrics */}
        <div className="flex items-center gap-3 text-xs">
          {hoveredNode ? (
            <div className="px-2.5 py-1 bg-purple-950 border border-purple-800 rounded text-purple-200 font-bold text-[11px] flex items-center gap-1.5">
              <span>Step {hoveredNode.step}:</span>
              <span className="text-white">{hoveredNode.label}</span>
              <span className="text-purple-400 text-[9px] uppercase">({hoveredNode.type})</span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-[11px]">Net Profit:</span>
              <span className="text-emerald-400 font-extrabold text-xs">
                +${route.netProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* SVG Canvas for D3 */}
      <div className="relative w-full overflow-hidden">
        <svg
          ref={svgRef}
          width="100%"
          height={height}
          className="w-full bg-slate-950/60 rounded-lg cursor-crosshair"
        />
      </div>

      {/* Footer Instructions */}
      <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-900">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span>Green = Token Node</span>
          <span className="ml-2 w-2 h-2 rounded-full bg-purple-500"></span>
          <span>Purple = DEX Pool Node</span>
        </span>
        <span className="text-slate-400">💡 Drag nodes to interactively inspect force simulation</span>
      </div>
    </div>
  );
};
